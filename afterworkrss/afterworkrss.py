import discord
from redbot.core import commands, Config, checks 
import logging
import asyncio
from datetime import datetime
from typing import Optional, Union, List
from urllib.parse import urlparse
import aiohttp
import feedparser
from bs4 import BeautifulSoup
import time
from types import SimpleNamespace

log = logging.getLogger("red.AfterworkRSS")

# --- UTILITY FUNCTIONS ---

def _get_admin_footer(obj: Union[commands.Context, discord.Interaction], status_action: str) -> str:
    """Helper to generate the administrative footer format."""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    user_display_name = obj.author.display_name if isinstance(obj, commands.Context) else obj.user.display_name
    return f"e.Network | {status_action} by {user_display_name} {current_time}"

async def _send_owner_dm(bot, message: str):
    """Sends a critical error message directly to the bot owner."""
    owner = bot.get_user(bot.owner_id)
    if owner:
        try:
            embed = discord.Embed(title="⚠️ Afterwork RSS Error", description=message, color=discord.Color.red())
            await owner.send(embed=embed)
        except discord.Forbidden:
            log.error(f"Failed to DM owner. Owner must enable DMs.")

async def _update_setup_embed(cog: commands.Cog, guild: discord.Guild, embed: discord.Embed):
    """Refreshes the configuration data shown in the setup embed."""
    settings = await cog.config.guild(guild).all()
    feeds_list = settings.get('feeds', [])
    is_enabled = settings.get('enabled', False)
    content_filters = settings.get('content_filters', [])

    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    
    feed_display = []
    for feed in feeds_list:
        channel = cog.bot.get_channel(feed['channel_id'])
        channel_name = f"#{channel.name}" if channel else "Unknown Channel"
        feed_display.append(f"• **{feed['name']}** -> {channel_name} ({feed['url'][:30]}...)")
    
    feed_display_str = "\n".join(feed_display) if feed_display else "*No feeds configured.*"
    filter_count = len(content_filters)
    
    embed.description = (
        "Configures RSS feeds to post updates in a specified channel. The core loop runs every 5 minutes."
    )
    embed.clear_fields()
    
    embed.add_field(name="System Status", value=status_emoji, inline=True)
    embed.add_field(name="Total Feeds Configured", value=str(len(feeds_list)), inline=True)
    embed.add_field(name="Active Filters", value=str(filter_count), inline=True)
    embed.add_field(name="Configured Feeds", value=feed_display_str, inline=False)
    
    return embed

# --- MODALS ---

class AddFeedModal(discord.ui.Modal, title="Add New RSS Feed"):
    feed_name_input = discord.ui.TextInput(
        label="Feed Name (e.g., 'Ark News')",
        style=discord.TextStyle.short,
        placeholder="A unique name to reference this feed.",
        required=True,
    )
    channel_id_input = discord.ui.TextInput(
        label="Target Channel ID", style=discord.TextStyle.short, placeholder="ID of the channel to post updates in.", required=True,
    )
    rss_url_input = discord.ui.TextInput(
        label="RSS/Atom Feed URL", style=discord.TextStyle.short, placeholder="e.g., https://store.steampowered.com/feeds/news/app/...", required=True,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message, backfill: bool = False):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message
        self.backfill = backfill
        if backfill: self.title = "Add RSS Feed (Post All History)"

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        feed_name = self.feed_name_input.value.strip().lower()
        channel_id_str = self.channel_id_input.value.strip()
        rss_url = self.rss_url_input.value.strip()
        
        try: channel_id = int(channel_id_str)
        except ValueError: return await interaction.followup.send("❌ **Error:** Channel ID must be a valid number.", ephemeral=True)
            
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await interaction.followup.send(f"❌ **Error:** Could not find a valid Text Channel or Thread with ID `{channel_id}`.", ephemeral=True)

        if not channel.permissions_for(interaction.guild.me).send_messages:
             return await interaction.followup.send(f"❌ **Error:** I do not have permission to post messages in {channel.mention}.", ephemeral=True)

        new_feed_data = await self.cog._add_feed_to_config(interaction.guild, feed_name, channel_id, rss_url, backfill=self.backfill)

        if isinstance(new_feed_data, str):
             return await interaction.followup.send(f"❌ **Error:** {new_feed_data}", ephemeral=True)

        async with self.cog.config.guild(interaction.guild).feeds() as feeds:
            feeds.append(new_feed_data)

        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, "Feed added"))
        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        view = SetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).enabled())
        await self.original_message.edit(embed=embed, view=view)
        
        mode = "and will start posting historical entries." if self.backfill else "and is now caught up."
        await interaction.followup.send(f"✅ Feed **{feed_name}** added for {channel.mention} {mode}", ephemeral=True)

class RemoveFeedModal(discord.ui.Modal, title="Remove RSS Feed"):
    feed_name_input = discord.ui.TextInput(
        label="Feed Name to Remove", style=discord.TextStyle.short, placeholder="The name of the feed (e.g., 'Ark News').", required=True,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300); self.cog = cog; self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        feed_name = self.feed_name_input.value.strip().lower()

        async with self.cog.config.guild(interaction.guild).feeds() as feeds:
            initial_len = len(feeds)
            feeds[:] = [f for f in feeds if f['name'] != feed_name]
            success = len(feeds) < initial_len

        if not success:
            return await interaction.followup.send(f"❌ **Error:** Feed **{feed_name}** not found.", ephemeral=True)
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"Feed '{feed_name}' removed"))
        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        view = SetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).enabled())
        await self.original_message.edit(embed=embed, view=view)
        
        await interaction.followup.send(f"✅ Feed **{feed_name}** removed.", ephemeral=True)

class AddFilterModal(discord.ui.Modal, title="Add Content Filter"):
    phrase_input = discord.ui.TextInput(label="Phrase to Filter", style=discord.TextStyle.short, placeholder="e.g., MODS SPOTLIGHT", required=True)
    
    def __init__(self, cog: commands.Cog, manager_interaction: discord.Interaction):
        super().__init__(timeout=300); self.cog = cog; self.manager_interaction = manager_interaction
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        phrase = self.phrase_input.value.strip()

        async with self.cog.config.guild(interaction.guild).content_filters() as filters:
            if phrase.lower() in [f.lower() for f in filters]:
                return await interaction.followup.send(f"⚠️ Filter **{phrase}** is already in the list.", ephemeral=True)
            filters.append(phrase)

        await self.cog.update_filter_panel(self.manager_interaction, "Filter added")
        await interaction.followup.send(f"✅ Filter added: **{phrase}**.", ephemeral=True)

class RemoveFilterModal(discord.ui.Modal, title="Remove Content Filter"):
    phrase_input = discord.ui.TextInput(label="Phrase to Remove", style=discord.TextStyle.short, placeholder="e.g., MODS SPOTLIGHT", required=True)

    def __init__(self, cog: commands.Cog, manager_interaction: discord.Interaction):
        super().__init__(timeout=300); self.cog = cog; self.manager_interaction = manager_interaction

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        phrase = self.phrase_input.value.strip()

        async with self.cog.config.guild(interaction.guild).content_filters() as filters:
            try:
                found_filter = next(f for f in filters if f.lower() == phrase.lower())
                filters.remove(found_filter)
                await self.cog.update_filter_panel(self.manager_interaction, "Filter removed")
                await interaction.followup.send(f"✅ Filter removed: **{found_filter}**.", ephemeral=True)
            except StopIteration:
                await interaction.followup.send(f"⚠️ Filter **{phrase}** was not found.", ephemeral=True)

# --- VIEWS ---

class FilterManagerView(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        super().__init__(timeout=300); self.cog = cog

    @discord.ui.button(label="Add Filter", style=discord.ButtonStyle.success, row=0)
    async def add_filter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddFilterModal(self.cog, interaction))

    @discord.ui.button(label="Remove Filter", style=discord.ButtonStyle.danger, row=0)
    async def remove_filter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveFilterModal(self.cog, interaction))

class SetupView(discord.ui.View):
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None); self.cog = cog
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    async def _check_owner(self, interaction: discord.Interaction):
        is_owner = await self.cog.bot.is_owner(interaction.user)
        if not is_owner: await interaction.response.send_message("Only the bot owner can use this feature.", ephemeral=False)
        return is_owner

    @discord.ui.button(label="Add New (Start NOW)", style=discord.ButtonStyle.primary, custom_id="rss_add_new_button", row=0)
    async def add_feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        await interaction.response.send_modal(AddFeedModal(self.cog, interaction.message, backfill=False))

    @discord.ui.button(label="Add and Backfill", style=discord.ButtonStyle.primary, custom_id="rss_add_backfill_button", row=0)
    async def add_and_backfill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        await interaction.response.send_modal(AddFeedModal(self.cog, interaction.message, backfill=True))

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, custom_id="rss_remove_feed_button", row=0)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        await interaction.response.send_modal(RemoveFeedModal(self.cog, interaction.message))

    @discord.ui.button(label="Toggle Status", style=discord.ButtonStyle.secondary, custom_id="rss_toggle_button", row=0)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        new_state = not (await self.cog.config.guild(interaction.guild).enabled())
        await self.cog.config.guild(interaction.guild).enabled.set(new_state)
        
        button.label, button.style = ("Disable", discord.ButtonStyle.danger) if new_state else ("Enable", discord.ButtonStyle.success)
        
        embed = interaction.message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"System {'enabled' if new_state else 'disabled'}"))
        
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await interaction.message.edit(embed=embed, view=self)
        
        await interaction.followup.send(f"System has been **{'enabled' if new_state else 'disabled'}**.", ephemeral=True)

    @discord.ui.button(label="Manage Filters", style=discord.ButtonStyle.secondary, custom_id="rss_manage_filters_button", row=1)
    async def manage_filters_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        await self.cog.send_filter_panel(interaction)


# --- MAIN COG CLASS ---

class AfterworkRSS(commands.Cog, name="AfterworkRSS"): 
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5577991122, force_registration=True) 
        self.config.register_guild(enabled=False, setup_message_id=None, feeds=[], content_filters=[])
        self._read_feeds_loop = None
        self._headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"}
        self._post_queue = asyncio.Queue()

    async def initialize(self):
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                self.bot.add_view(SetupView(self, initial_enabled=data.get('enabled', False)), message_id=data['setup_message_id'])
        self.start_background_loop()

    def start_background_loop(self):
        if not self._read_feeds_loop: self._read_feeds_loop = self.bot.loop.create_task(self.read_feeds())

    def cog_unload(self):
        if self._read_feeds_loop: self._read_feeds_loop.cancel()

    @commands.group(name="afterworkrss")
    @commands.is_owner()
    async def afterworkrss(self, ctx: commands.Context):
        """The Afterwork RSS Configuration Panel."""
        if ctx.invoked_subcommand is None: await ctx.send_help()

    @afterworkrss.command(name="deploy")
    @commands.is_owner()
    async def afterworkrss_deploy(self, ctx: commands.Context):
        """Deploys or redeploys the persistent administrative configuration hub."""
        old_message_id = await self.config.guild(ctx.guild).setup_message_id()
        if old_message_id:
            try: await ctx.channel.fetch_message(old_message_id).delete()
            except discord.HTTPException: pass

        initial_embed = discord.Embed(title="RSS Feed Control", color=discord.Color.blue())
        initial_embed = await _update_setup_embed(self, ctx.guild, initial_embed)
        initial_enabled = await self.config.guild(ctx.guild).enabled()
        initial_embed.set_footer(text=_get_admin_footer(ctx, "Configuration Hub Deployed"))

        view = SetupView(self, initial_enabled=initial_enabled)
        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        await sent_message.pin(reason="Afterwork RSS Configuration Hub.")
        await self.config.guild(ctx.guild).setup_message_id.set(sent_message.id)
        
        await ctx.message.delete()
        await asyncio.sleep(1)
        try: # Delete pin notification message
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete(); break
        except Exception: pass

    async def send_filter_panel(self, interaction: discord.Interaction):
        """Sends the ephemeral filter management panel."""
        filters = await self.config.guild(interaction.guild).content_filters()
        filter_list_display = "No active filters."
        if filters: filter_list_display = "\n".join([f"- {f}" for f in filters])
        
        embed = discord.Embed(title="Content Filter Management", description=filter_list_display, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=FilterManagerView(self), ephemeral=True)

    async def update_filter_panel(self, interaction: discord.Interaction, status: str):
        """Updates the ephemeral filter panel after an action."""
        filters = await self.config.guild(interaction.guild).content_filters()
        filter_list_display = "No active filters."
        if filters: filter_list_display = "\n".join([f"- {f}" for f in filters])
        
        embed = discord.Embed(title="Content Filter Management", description=filter_list_display, color=discord.Color.blue())
        embed.set_footer(text=f"Last Action: {status}")
        await interaction.message.edit(embed=embed)
        
        setup_message_id = await self.config.guild(interaction.guild).setup_message_id()
        if setup_message_id:
            try:
                setup_message = await interaction.channel.fetch_message(setup_message_id)
                main_embed = setup_message.embeds[0]
                await _update_setup_embed(self, interaction.guild, main_embed)
                await setup_message.edit(embed=main_embed)
            except (discord.NotFound, discord.Forbidden):
                pass
    
    # --- Core RSS Logic ---
    
    async def _add_feed_to_config(self, guild: discord.Guild, feed_name: str, channel_id: int, url: str, backfill: bool = False) -> Union[dict, str]:
        """Validates, fetches initial post, and creates the new feed entry dict."""
        feeds_list = await self.config.guild(guild).feeds()
        if any(f['name'] == feed_name for f in feeds_list):
            return "A feed with that name already exists."
        
        try:
            feedparser_obj = await self._fetch_feedparser_object(url)
        except Exception as e:
            return f"Failed to fetch or parse the RSS feed: {e}"

        entry = feedparser_obj.entries[0] if feedparser_obj.entries else feedparser_obj.feed
        entry_time = self._time_tag_validation(entry)
        last_time = entry_time if not backfill else 0
        
        return {
            "name": feed_name, "channel_id": channel_id, "url": url,
            "last_title": entry.get("title", ""), "last_link": entry.get("link", ""),
            "last_time": last_time, "template": "**$title**\n$summary_detail_plaintext\n$link", "is_embed": True
        }

    async def _fetch_feedparser_object(self, url: str) -> SimpleNamespace:
        """Downloads and parses the feed."""
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(headers=self._headers, timeout=timeout) as session:
                async with session.get(url) as resp:
                    html = await resp.read()
            
            feedparser_obj = feedparser.parse(html)
            if feedparser_obj.bozo:
                soup = BeautifulSoup(html, 'html.parser')
                error_msg = f"Bozo feed: {feedparser_obj.bozo_exception}. HTML Snippet: {soup.prettify()[:200]}..."
                raise ValueError(error_msg)
            return feedparser_obj
        except Exception as e:
            raise Exception(f"Feed fetch failed: {e}")

    def _time_tag_validation(self, entry: SimpleNamespace) -> Optional[int]:
        """Gets a unix timestamp from the entry."""
        entry_time = entry.get("updated_parsed", entry.get("published_parsed"))
        if isinstance(entry_time, time.struct_time): return int(time.mktime(entry_time))
        return None
        
    async def _update_last_scraped(self, feed_name: str, guild_id: int, title: str, link: str, entry_time: int):
        """Updates the last successful check time/content in the config."""
        async with self.config.guild(guild_id).feeds() as feeds:
             for feed in feeds:
                if feed['name'] == feed_name:
                    feed['last_title'], feed['last_link'], feed['last_time'] = title, link, entry_time
                    break
        
    # --- Background Loop ---

    async def read_feeds(self):
        """The core background loop that processes all feeds."""
        await self.bot.wait_until_red_ready()
        
        while True:
            await asyncio.sleep(300) 
            
            for guild_id, guild_data in (await self.config.all_guilds()).items():
                if not guild_data.get('enabled'): continue
                guild = self.bot.get_guild(guild_id)
                if not guild or guild.unavailable: continue
                
                for feed in guild_data.get('feeds', []):
                    try: await self.check_and_post_feed(guild, feed)
                    except Exception as e: log.error(f"Error processing feed {feed['name']} in {guild.name}: {e}", exc_info=True)
                         
    async def check_and_post_feed(self, guild: discord.Guild, feed: dict):
        channel = self.bot.get_channel(feed['channel_id'])
        if not channel or not channel.permissions_for(guild.me).send_messages: return

        feedparser_obj = await self._fetch_feedparser_object(feed['url'])
        if not feedparser_obj.entries: return

        content_filters = await self.config.guild(guild).content_filters()
        
        entries_to_post = []
        for entry in feedparser_obj.entries:
            current_time = self._time_tag_validation(entry)
            is_new = (feed['last_time'] == 0) or (current_time and feed['last_time'] and current_time > feed['last_time'])
            
            if is_new:
                entries_to_post.append((entry, entry.get("title", ""), entry.get("link", ""), current_time))
            
            if feed['last_time'] != 0 and current_time and current_time <= feed['last_time']:
                break
        
        if not entries_to_post: return

        entries_to_post.reverse()
        newest_post_time, newest_post_title, newest_post_link = 0, "", ""
        
        DESCRIPTION_LIMIT = 4096 
        
        for entry, current_title, current_link, current_time in entries_to_post:
            
            if current_time and current_time > newest_post_time:
                newest_post_time, newest_post_title, newest_post_link = current_time, current_title, current_link
            
            summary_html = entry.get("summary_detail", {}).get("value", "") or entry.get("content", [{}])[0].get("value", "")
            summary_text = BeautifulSoup(summary_html, 'html.parser').get_text()

            for phrase in content_filters:
                if phrase.lower() in summary_text.lower():
                    summary_text = summary_text.split(phrase, 1)[0].strip()
                    break
            
            if len(summary_text) > DESCRIPTION_LIMIT:
                summary_text = summary_text[:DESCRIPTION_LIMIT - 60] + f"\n\n[... Read Full Post Here]({current_link})"
            
            if feed['is_embed']:
                embed = discord.Embed(title=current_title, description=summary_text, url=current_link, color=discord.Color.blue())
                if current_time: embed.timestamp = datetime.fromtimestamp(current_time)
                try: await channel.send(embed=embed)
                except discord.Forbidden: return
            else:
                message = f"**{current_title}**\n{summary_text}\n{current_link}"
                try: await channel.send(message)
                except discord.Forbidden: return

        if newest_post_time > 0 and newest_post_time > feed['last_time']:
            await self._update_last_scraped(feed['name'], guild.id, newest_post_title, newest_post_link, newest_post_time)

async def setup(bot):
    cog = AfterworkRSS(bot) 
    await cog.initialize()
    await bot.add_cog(cog)

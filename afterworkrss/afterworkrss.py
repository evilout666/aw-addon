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
    
    # Generate list of saved feeds
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
        max_length=50,
    )
    channel_id_input = discord.ui.TextInput(
        label="Target Channel ID (Numbers Only)",
        style=discord.TextStyle.short,
        placeholder="ID of the channel to post updates in.",
        required=True,
        max_length=20,
    )
    rss_url_input = discord.ui.TextInput(
        label="RSS/Atom Feed URL",
        style=discord.TextStyle.short,
        placeholder="e.g., https://store.steampowered.com/feeds/news/app/...",
        required=True,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message, backfill: bool = False):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message
        self.backfill = backfill
        if backfill:
             self.title = "Add RSS Feed (Post All History)"

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        feed_name = self.feed_name_input.value.strip().lower()
        channel_id_str = self.channel_id_input.value.strip()
        rss_url = self.rss_url_input.value.strip()
        
        try: channel_id = int(channel_id_str)
        except ValueError:
            return await interaction.followup.send("❌ **Error:** Channel ID must be a valid number.", ephemeral=True)
            
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await interaction.followup.send(f"❌ **Error:** Could not find a valid Text Channel or Thread with ID `{channel_id}`.", ephemeral=True)

        if not channel.permissions_for(interaction.guild.me).send_messages:
             return await interaction.followup.send(f"❌ **Error:** I do not have permission to post messages in {channel.mention}.", ephemeral=True)

        # Attempt to initialize and validate feed, passing the backfill flag
        new_feed_data = await self.cog._add_feed_to_config(interaction.guild, feed_name, channel_id, rss_url, backfill=self.backfill)

        if isinstance(new_feed_data, str):
             return await interaction.followup.send(f"❌ **Error:** {new_feed_data}", ephemeral=True)

        # Save the new configuration
        async with self.cog.config.guild(interaction.guild).feeds() as feeds:
            feeds.append(new_feed_data)

        # Update the original setup message to reflect the change
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, "Feed added"))
        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        view = SetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).enabled())
        await self.original_message.edit(embed=embed, view=view)
        
        mode = "and will start posting historical entries." if self.backfill else "and is now caught up."
        await interaction.followup.send(f"✅ Feed **{feed_name}** added for {channel.mention} {mode}", ephemeral=True)

class RemoveFeedModal(discord.ui.Modal, title="Remove RSS Feed"):
    feed_name_input = discord.ui.TextInput(
        label="Feed Name to Remove",
        style=discord.TextStyle.short,
        placeholder="The name of the feed (e.g., 'Ark News').",
        required=True,
        max_length=50,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        feed_name = self.feed_name_input.value.strip().lower()

        async with self.cog.config.guild(interaction.guild).feeds() as feeds:
            initial_len = len(feeds)
            feeds[:] = [f for f in feeds if f['name'] != feed_name]
            
            if len(feeds) < initial_len:
                success = True
            else:
                success = False

        if not success:
            return await interaction.followup.send(f"❌ **Error:** Feed **{feed_name}** not found.", ephemeral=True)
        
        # Update the original setup message
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"Feed '{feed_name}' removed"))
        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        view = SetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).enabled())
        await self.original_message.edit(embed=embed, view=view)
        
        await interaction.followup.send(f"✅ Feed **{feed_name}** removed.", ephemeral=True)

class ManageFilterModal(discord.ui.Modal, title="Content Filter Management"):
    # FIX APPLIED: Removed 'disabled=True' to fix TypeError
    filter_instruction = discord.ui.TextInput(
        label="Active Filters and Commands",
        style=discord.TextStyle.long,
        default="Use the following commands in chat to manage filters:\n\n"
                "[p]afterworkrss filters list\n"
                "[p]afterworkrss filters add <phrase>\n"
                "[p]afterworkrss filters remove <phrase>",
        required=False,
        max_length=1000,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message, current_filters: List[str]):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message
        
        filter_list_display = "No active filters."
        if current_filters:
            filter_list_display = "\n".join([f"- {f}" for f in current_filters])
        
        full_message = (
            f"Current Filters:\n{filter_list_display}\n\n"
            f"Use the commands below in chat to modify this list (replace [p] with your prefix):\n"
            f"[p]afterworkrss filters list\n"
            f"[p]afterworkrss filters add \"<phrase>\"\n"
            f"[p]afterworkrss filters remove \"<phrase>\""
        )
        self.filter_instruction.default = full_message
        self.add_item(self.filter_instruction)

    async def on_submit(self, interaction: discord.Interaction):
        # Submission doesn't do anything but acknowledge the user read the instructions
        await interaction.response.send_message("Filters are managed using the commands listed above.", ephemeral=True)


# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    async def _check_owner(self, interaction: discord.Interaction):
        is_owner = await self.cog.bot.is_owner(interaction.user)
        if not is_owner:
            await interaction.response.send_message("Only the bot owner can use this feature.", ephemeral=False)
        return is_owner

    @discord.ui.button(label="Add New (Start NOW)", style=discord.ButtonStyle.primary, custom_id="rss_add_new_button", row=0)
    async def add_feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        modal = AddFeedModal(self.cog, interaction.message, backfill=False)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Add and Backfill", style=discord.ButtonStyle.primary, custom_id="rss_add_backfill_button", row=0)
    async def add_and_backfill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        modal = AddFeedModal(self.cog, interaction.message, backfill=True)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, custom_id="rss_remove_feed_button", row=0)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        modal = RemoveFeedModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Toggle Status", style=discord.ButtonStyle.secondary, custom_id="rss_toggle_button", row=0)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        new_state = not (await self.cog.config.guild(interaction.guild).enabled())
        await self.cog.config.guild(interaction.guild).enabled.set(new_state)
        
        button.label = "Disable" if new_state else "Enable"
        button.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success
        
        embed = interaction.message.embeds[0]
        status_msg = f"System {'enabled' if new_state else 'disabled'}"
        embed.set_footer(text=_get_admin_footer(interaction, status_msg))
        
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await interaction.message.edit(embed=embed, view=self)
        
        await interaction.followup.send(f"System has been **{'enabled' if new_state else 'disabled'}**.", ephemeral=True)

    @discord.ui.button(label="Manage Filters", style=discord.ButtonStyle.secondary, custom_id="rss_manage_filters_button", row=1)
    async def manage_filters_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        current_filters = await self.cog.config.guild(interaction.guild).content_filters()
        modal = ManageFilterModal(self.cog, interaction.message, current_filters)
        await interaction.response.send_modal(modal)

# --- MAIN COG CLASS (Adapted for simplicity) ---

class AfterworkRSS(commands.Cog, name="AfterworkRSS"): 
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5577991122, force_registration=True) 
        self.config.register_guild(
            enabled=False,
            setup_message_id=None,
            feeds=[], 
            content_filters=[], 
        )
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
        if not self._read_feeds_loop:
             self._read_feeds_loop = self.bot.loop.create_task(self.read_feeds())

    def cog_unload(self):
        if self._read_feeds_loop: self._read_feeds_loop.cancel()

    # --- BRANDED TOP-LEVEL COMMAND GROUP ---
    @commands.group(invoke_without_command=False, name="afterworkrss")
    @commands.is_owner()
    async def afterworkrss(self, ctx):
        """The Afterwork RSS Configuration Panel."""
        # The 'deploy' subcommand handles showing the panel

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
                    await message.delete()
                    break
        except Exception: pass

    @afterworkrss.command(name="removefeed")
    @checks.mod_or_permissions(manage_guild=True)
    async def afterworkrss_removefeed(self, ctx, feed_name: str):
        """Removes an RSS feed by its configured name (Command line utility)."""
        feed_name = feed_name.lower()
        
        async with self.config.guild(ctx.guild).feeds() as feeds:
            initial_len = len(feeds)
            feeds[:] = [f for f in feeds if f['name'] != feed_name]
            
            if len(feeds) < initial_len:
                await ctx.send(f"✅ Feed **{feed_name}** removed.")
            else:
                await ctx.send(f"❌ Feed **{feed_name}** not found.")

    # --- FILTER MANAGEMENT COMMAND GROUP ---
    
    @afterworkrss.group(name="filters")
    @checks.mod_or_permissions(manage_guild=True)
    async def afterworkrss_filters(self, ctx: commands.Context):
        """Manages the list of phrases removed from Steam news post bodies."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @afterworkrss_filters.command(name="list")
    async def afterworkrss_filters_list(self, ctx: commands.Context):
        """Lists all active content filters."""
        filters = await self.config.guild(ctx.guild).content_filters()
        if not filters:
            return await ctx.send("No content filters are currently active.")
        
        msg = "Active Content Filters (Phrases that trigger section removal):\n"
        for i, f in enumerate(filters, 1):
            msg += f"{i}. {f}\n"
        
        await ctx.send(box(msg, lang="ini"))

    @afterworkrss_filters.command(name="add")
    async def afterworkrss_filters_add(self, ctx: commands.Context, *, phrase: str):
        """Adds a phrase that will be removed from the body of posts."""
        phrase = phrase.strip()
        if not phrase:
            return await ctx.send("Please provide a phrase to filter.")
            
        async with self.config.guild(ctx.guild).content_filters() as filters:
            # Case-insensitive check to avoid duplicates with different casing
            if phrase.lower() in [f.lower() for f in filters]:
                return await ctx.send(f"⚠️ Filter **{phrase}** is already in the list.")

            filters.append(phrase)
            await ctx.send(f"✅ Filter added: **{phrase}**. All content following this phrase will be removed from future posts.")

    @afterworkrss_filters.command(name="remove")
    async def afterworkrss_filters_remove(self, ctx: commands.Context, *, phrase: str):
        """Removes a phrase from the content filter list."""
        phrase = phrase.strip()
        
        async with self.config.guild(ctx.guild).content_filters() as filters:
            try:
                # Find the filter using case-insensitive matching
                found_filter = next(f for f in filters if f.lower() == phrase.lower())
                filters.remove(found_filter)
                await ctx.send(f"✅ Filter removed: **{found_filter}**.")
            except StopIteration:
                await ctx.send(f"⚠️ Filter **{phrase}** was not found in the list.")


    # --- Core RSS Logic (Simplified) ---
    
    async def _add_feed_to_config(self, guild: discord.Guild, feed_name: str, channel_id: int, url: str, backfill: bool = False) -> Union[dict, str]:
        """Validates, fetches initial post, and creates the new feed entry dict."""
        feeds_list = await self.config.guild(guild).feeds()
        if any(f['name'] == feed_name for f in feeds_list):
            return "A feed with that name already exists."
        
        try:
            feedparser_obj = await self._fetch_feedparser_object(url)
        except Exception as e:
            log.error(f"Failed to fetch initial feed {url}: {e}", exc_info=True)
            return "Failed to fetch or parse the RSS feed URL. Check if it is a valid RSS/Atom link."

        # Use the newest entry or fallback to feed metadata
        entry = feedparser_obj.entries[0] if feedparser_obj.entries else feedparser_obj.feed
        
        entry_time = self._time_tag_validation(entry)
        
        # If backfill is TRUE, set last_time to 0 to force posting all found entries.
        last_time = entry_time if not backfill else 0
        
        new_feed_data = {
            "name": feed_name,
            "channel_id": channel_id,
            "url": url,
            "last_title": entry.get("title", ""),
            "last_link": entry.get("link", ""),
            "last_time": last_time,
            "template": "**$title**\n$summary_detail_plaintext\n$link",
            "is_embed": True
        }
        return new_feed_data

    async def _fetch_feedparser_object(self, url: str) -> SimpleNamespace:
        """Downloads and parses the feed."""
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(headers=self._headers, timeout=timeout) as session:
                async with session.get(url) as resp:
                    # Use BeautifulSoup for initial check, as it will handle some non-standard feeds better
                    html = await resp.read()
            
            feedparser_obj = feedparser.parse(html)
            if feedparser_obj.bozo:
                # Use bs4 to give a slightly clearer error message
                soup = BeautifulSoup(html, 'html.parser')
                error_msg = f"Bozo feed: {feedparser_obj.bozo_exception}. HTML Snippet: {soup.prettify()[:200]}..."
                raise ValueError(error_msg)
                
            return feedparser_obj
        except Exception as e:
            raise Exception(f"Feed fetch failed: {e}")

    def _time_tag_validation(self, entry: SimpleNamespace) -> Optional[int]:
        """Gets a unix timestamp from the entry, preferring `updated_parsed`."""
        entry_time = entry.get("updated_parsed", entry.get("published_parsed"))
        if isinstance(entry_time, time.struct_time):
            return int(time.mktime(entry_time))
        return None
        
    async def _update_last_scraped(self, feeds_list: List[dict], feed_name: str, guild_id: int, title: str, link: str, entry_time: int):
        """Updates the last successful check time/content in the config."""
        async with self.config.guild(guild_id).feeds() as feeds:
             for feed in feeds:
                if feed['name'] == feed_name:
                    feed['last_title'] = title
                    feed['last_link'] = link
                    feed['last_time'] = entry_time
                    break
        
    # --- Background Loop ---

    async def read_feeds(self):
        """The core background loop that processes all feeds."""
        await self.bot.wait_until_red_ready()
        
        # Simple loop structure: check all feeds sequentially every 5 minutes (300 seconds)
        while True:
            await asyncio.sleep(300) # Wait interval
            
            for guild_id, guild_data in (await self.config.all_guilds()).items():
                if not guild_data.get('enabled'): continue
                
                guild = self.bot.get_guild(guild_id)
                if not guild or guild.unavailable: continue
                
                feeds_to_check = guild_data.get('feeds', [])
                for feed in feeds_to_check:
                    try:
                        await self.check_and_post_feed(guild, feed)
                    except Exception as e:
                         log.error(f"Error processing feed {feed['name']} in {guild.name}: {e}", exc_info=True)
                         
    async def check_and_post_feed(self, guild: discord.Guild, feed: dict):
        channel = self.bot.get_channel(feed['channel_id'])
        if not channel or not channel.permissions_for(guild.me).send_messages: 
            return # Skip feed if channel is unavailable or missing permissions

        feedparser_obj = await self._fetch_feedparser_object(feed['url'])
        if not feedparser_obj.entries: return

        # Get active filters
        content_filters = await self.config.guild(guild).content_filters()
        
        # Iterate through all entries in reverse (newest first)
        entries_to_post = []
        for entry in feedparser_obj.entries:
            current_title = entry.get("title", "")
            current_link = entry.get("link", "")
            current_time = self._time_tag_validation(entry)

            # Comparison Logic: Check if the post is newer than the last recorded time
            is_new_entry = False
            
            # If last_time is 0 (backfill mode), we post everything.
            if feed['last_time'] == 0:
                is_new_entry = True
            
            # Standard mode check: Is the current time newer than the last recorded time?
            elif current_time and feed['last_time'] and current_time > feed['last_time']:
                is_new_entry = True
                
            # Fallback check (for feeds with unstable timestamps)
            elif feed['last_title'] != current_title or feed['last_link'] != current_link:
                 if feed['last_time'] == 0: # Only post if in backfill mode
                    is_new_entry = True


            if is_new_entry:
                entries_to_post.append((entry, current_title, current_link, current_time))
            
            # Once we hit a post older than the last recorded time, stop.
            if feed['last_time'] != 0 and current_time and current_time <= feed['last_time']:
                break

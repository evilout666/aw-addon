import discord
from redbot.core import commands, Config, checks # <-- FIX APPLIED HERE
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

    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    
    # Generate list of saved feeds
    feed_display = []
    for feed in feeds_list:
        channel = cog.bot.get_channel(feed['channel_id'])
        channel_name = f"#{channel.name}" if channel else "Unknown Channel"
        feed_display.append(f"• **{feed['name']}** -> {channel_name} ({feed['url'][:30]}...)")
    
    feed_display_str = "\n".join(feed_display) if feed_display else "*No feeds configured.*"
    
    embed.description = (
        "Configures RSS feeds to post updates in a specified channel. The core loop runs every 5 minutes."
    )
    embed.clear_fields()
    
    embed.add_field(name="System Status", value=status_emoji, inline=True)
    embed.add_field(name="Total Feeds Configured", value=str(len(feeds_list)), inline=True)
    embed.add_field(name="Configured Feeds", value=feed_display_str, inline=False)
    
    return embed

# --- MODALS ---

class AddFeedModal(discord.ui.Modal, title="Add New RSS Feed"):
    feed_name_input = discord.ui.TextInput(
        label="Feed Name (e.g., 'GitHub News')",
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
        placeholder="e.g., https://github.com/red-cog/feed.xml",
        required=True,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

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

        # Attempt to initialize and validate feed
        new_feed_data = await self.cog._add_feed_to_config(interaction.guild, feed_name, channel_id, rss_url)

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
        
        await interaction.followup.send(f"✅ Feed **{feed_name}** added for {channel.mention}.", ephemeral=True)

# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    def _check_owner(self, interaction: discord.Interaction):
        if interaction.user.id != self.cog.bot.owner_id: 
            asyncio.create_task(interaction.response.send_message("Only the bot owner can use this feature.", ephemeral=False))
            return False
        return True

    @discord.ui.button(label="Add Feed", style=discord.ButtonStyle.primary, custom_id="rss_add_feed_button", row=0)
    async def add_feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_owner(interaction): return
        modal = AddFeedModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove Feed (Command)", style=discord.ButtonStyle.secondary, custom_id="rss_remove_feed_button", row=0)
    async def remove_feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_owner(interaction): return
        await interaction.response.send_message("Please use a command like `[p]rssremove <name>` to delete feeds.", ephemeral=True)

    @discord.ui.button(label="Toggle Status", style=discord.ButtonStyle.secondary, custom_id="rss_toggle_button", row=1)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._check_owner(interaction): return
        
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

# --- MAIN COG CLASS (Adapted for simplicity) ---

class AfterworkRSS(commands.Cog, name="AfterworkRSS"): 
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5577991122, force_registration=True) 
        self.config.register_guild(
            enabled=False,
            setup_message_id=None,
            feeds=[], # List of dictionaries, each describing a feed
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

    @commands.command(name="afterworkrss") 
    @commands.is_owner()
    async def afterworkrss_command(self, ctx: commands.Context):
        """Deploys or redeploys the persistent administrative configuration hub for RSS feeds."""
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

    @commands.command(name="rssremove")
    @checks.mod_or_permissions(manage_guild=True)
    async def rssremove(self, ctx, feed_name: str):
        """Removes an RSS feed by its configured name."""
        feed_name = feed_name.lower()
        
        async with self.config.guild(ctx.guild).feeds() as feeds:
            initial_len = len(feeds)
            feeds[:] = [f for f in feeds if f['name'] != feed_name]
            
            if len(feeds) < initial_len:
                await ctx.send(f"✅ Feed **{feed_name}** removed.")
            else:
                await ctx.send(f"❌ Feed **{feed_name}** not found.")

    # --- Core RSS Logic (Simplified) ---
    
    async def _add_feed_to_config(self, guild: discord.Guild, feed_name: str, channel_id: int, url: str) -> Union[dict, str]:
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
        
        new_feed_data = {
            "name": feed_name,
            "channel_id": channel_id,
            "url": url,
            "last_title": entry.get("title", ""),
            "last_link": entry.get("link", ""),
            "last_time": entry_time,
            "template": "**$title**\n$link",
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

        # Get the newest entry and sort it to compare
        entry = feedparser_obj.entries[0]
        
        current_title = entry.get("title", "")
        current_link = entry.get("link", "")
        current_time = self._time_tag_validation(entry)
        
        # Comparison Logic: Check if the post is genuinely new
        is_new_entry = False
        if current_time and feed['last_time'] and current_time > feed['last_time']:
            is_new_entry = True
        elif feed['last_title'] != current_title or feed['last_link'] != current_link:
            is_new_entry = True

        if is_new_entry:
            # Post the new content
            message = feed['template'].replace('$title', current_title).replace('$link', current_link)
            
            if feed['is_embed']:
                embed = discord.Embed(title=current_title, description=current_link, color=discord.Color.blue())
                if current_time: embed.timestamp = datetime.fromtimestamp(current_time)
                try: await channel.send(embed=embed)
                except discord.Forbidden: return
            else:
                try: await channel.send(f"{message}")
                except discord.Forbidden: return

            # Update the last checked status in config
            await self._update_last_scraped(None, feed['name'], guild.id, current_title, current_link, current_time)

async def setup(bot):
    cog = AfterworkRSS(bot) 
    await cog.initialize()
    await bot.add_cog(cog)

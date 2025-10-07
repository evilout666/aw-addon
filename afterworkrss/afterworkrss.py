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
    feed_name = discord.ui.TextInput(label="Feed Name", placeholder="e.g., RedBot News", required=True)
    feed_url = discord.ui.TextInput(label="RSS Feed URL", placeholder="e.g., https://example.com/rss", required=True)
    channel_id = discord.ui.TextInput(label="Target Channel ID", placeholder="ID of the channel to post updates to", required=True)
    is_embed = discord.ui.TextInput(label="Use Embeds? (Y/N)", default="Y", max_length=1, required=True)

    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        name = self.feed_name.value.strip().lower()
        url = self.feed_url.value.strip()
        
        try:
            channel_id = int(self.channel_id.value.strip())
        except ValueError:
            return await interaction.followup.send("❌ Channel ID must be a valid number.", ephemeral=True)
            
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("❌ Channel not found or is not a text channel.", ephemeral=True)
        
        is_embed_bool = self.is_embed.value.strip().lower() == 'y'

        new_feed = {
            'name': name,
            'url': url,
            'channel_id': channel_id,
            'is_embed': is_embed_bool,
            'last_time': 0 
        }
        
        async with self.cog.config.guild(interaction.guild).feeds() as feeds:
            if any(f['name'].lower() == name for f in feeds):
                return await interaction.followup.send(f"❌ Feed '{name}' already exists.", ephemeral=True)
            feeds.append(new_feed)

        # Update UI (Silent Success)
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"Feed '{name}' added"))
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await self.original_message.edit(embed=embed, view=SetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).enabled()))
        # The thinking state is implicitly cleared by the message edit
        

class RemoveFeedModal(discord.ui.Modal, title="Remove RSS Feed"):
    feed_name = discord.ui.TextInput(label="Feed Name to Remove", placeholder="e.g., RedBot News", required=True)

    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        name_to_remove = self.feed_name.value.strip().lower()
        
        initial_count = 0
        async with self.cog.config.guild(interaction.guild).feeds() as feeds:
            initial_count = len(feeds)
            feeds[:] = [f for f in feeds if f['name'].lower() != name_to_remove]
        
        if len(self.cog.config.guild(interaction.guild).feeds()) == initial_count:
            return await interaction.followup.send(f"❌ Feed '{name_to_remove}' not found.", ephemeral=True)

        # Update UI (Silent Success)
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"Feed '{name_to_remove}' removed"))
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await self.original_message.edit(embed=embed, view=SetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).enabled()))
        # The thinking state is implicitly cleared by the message edit


class AddFilterModal(discord.ui.Modal, title="Add Content Filter"):
    filter_text = discord.ui.TextInput(label="Text to Filter", placeholder="e.g., sponsored post, check out my video", required=True)

    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        text_to_filter = self.filter_text.value.strip()
        
        async with self.cog.config.guild(interaction.guild).content_filters() as filters:
            if text_to_filter.lower() in [f.lower() for f in filters]:
                 return await interaction.followup.send(f"⚠️ Filter '{text_to_filter}' already exists.", ephemeral=True)
            filters.append(text_to_filter)

        # Update UI (Silent Success)
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"Filter added"))
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await self.original_message.edit(embed=embed, view=SetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).enabled()))
        # The thinking state is implicitly cleared by the message edit

# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    @discord.ui.button(label="Add Feed", style=discord.ButtonStyle.primary, custom_id="rss_add_feed", row=0)
    async def add_feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        modal = AddFeedModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove Feed", style=discord.ButtonStyle.secondary, custom_id="rss_remove_feed", row=0)
    async def remove_feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        modal = RemoveFeedModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Add Filter", style=discord.ButtonStyle.secondary, custom_id="rss_add_filter", row=1)
    async def add_filter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        modal = AddFilterModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Toggle System", style=discord.ButtonStyle.secondary, custom_id="rss_toggle_system", row=1)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        
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
        
        # FIX: Removed the incorrect interaction.followup.defer() call

# --- MAIN COG CLASS ---

class AfterworkRSS(commands.Cog, name="AfterworkRSS"): 
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5577991122, force_registration=True) 
        self.config.register_guild(enabled=False, setup_message_id=None, feeds=[], content_filters=[])
        self._read_feeds_loop = None
        self._headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"}

    async def initialize(self):
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                guild = self.bot.get_guild(guild_id)
                if guild:
                    initial_enabled = data.get('enabled', False)
                    self.bot.add_view(SetupView(self, initial_enabled=initial_enabled), message_id=data['setup_message_id'])
        self.start_background_loop()

    def start_background_loop(self):
        # NOTE: Placeholder for actual read_feeds logic
        if not self._read_feeds_loop: 
            self._read_feeds_loop = self.bot.loop.create_task(self._read_feeds_task()) 

    def cog_unload(self):
        if self._read_feeds_loop: self._read_feeds_loop.cancel()
        
    async def _read_feeds_task(self):
        # Placeholder for the actual periodic task loop logic
        await self.bot.wait_until_ready()
        while self.bot.is_ready():
            # Actual feed checking logic would go here
            await asyncio.sleep(300) # Check every 5 minutes

    @commands.group(name="afterworkrss")
    @commands.is_owner()
    async def afterworkrss_group(self, ctx: commands.Context):
        """Management commands for the AfterworkRSS cog."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @afterworkrss_group.command(name="deploy")
    async def afterworkrss_deploy(self, ctx: commands.Context):
        """Deploys the persistent configuration hub for Afterwork RSS."""
        bot_member = ctx.guild.get_member(self.bot.user.id)
        perms = ctx.channel.permissions_for(bot_member)
        if not perms.send_messages or not perms.manage_messages:
            await _send_owner_dm(self.bot, f"Config failed in **{ctx.guild.name}**. Need Send/Manage Messages in **#{ctx.channel.name}**.")
            return
        
        old_message_id = await self.config.guild(ctx.guild).setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException: pass
            
        initial_embed = discord.Embed(title="RSS Feed Control", color=discord.Color.blue())
        initial_embed = await _update_setup_embed(self, ctx.guild, initial_embed)
        initial_embed.set_footer(text=_get_admin_footer(ctx, "Configuration Hub Deployed"))
        initial_enabled = await self.config.guild(ctx.guild).enabled()
        
        view = SetupView(self, initial_enabled=initial_enabled)
        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        await sent_message.pin(reason="Afterwork RSS Configuration Hub.")
        await self.config.guild(ctx.guild).setup_message_id.set(sent_message.id)
        
        await ctx.message.delete()
        await asyncio.sleep(1)
        try:
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception: pass
        
    # NOTE: The check_and_post_feed and other internal methods from the original file are assumed to be present.

async def setup(bot):
    cog = AfterworkRSS(bot) 
    await cog.initialize()
    await bot.add_cog(cog)

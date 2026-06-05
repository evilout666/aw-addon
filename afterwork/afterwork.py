import discord
from redbot.core import commands, Config
import logging
import asyncio
import re
import time
import json
from datetime import datetime
from typing import Optional, Union, List
from urllib.parse import urlparse
import aiohttp
import feedparser
from bs4 import BeautifulSoup
from types import SimpleNamespace
import lavalink

log = logging.getLogger("red.Afterwork")

# --- UTILITY FUNCTIONS ---

def _get_admin_footer(obj: Union[commands.Context, discord.Interaction], status_action: str) -> str:
    """Helper to generate the administrative footer format."""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    user_display_name = obj.author.display_name if isinstance(obj, commands.Context) else obj.user.display_name
    return f"e.Network | {status_action} by {user_display_name} {current_time}"

async def _send_owner_dm(bot, message: str):
    """Sends a critical error message directly to the bot owner."""
    owner_id = bot.owner_id
    owner = bot.get_user(owner_id)
    if owner:
        try:
            embed = discord.Embed(
                title="⚠️ Afterwork Error Notification",
                description=message,
                color=discord.Color.red()
            )
            await owner.send(embed=embed)
        except discord.Forbidden:
            log.error("Failed to DM owner. Owner must enable DMs.")

# --- DYNAMIC SETUP EMBED UPDATERS ---

async def _update_audio_setup_embed(cog, guild: discord.Guild, embed: discord.Embed):
    settings = await cog.config.guild(guild).all()
    is_enabled = settings.get('audio_is_enabled', False)
    vc_id = settings.get('audio_music_voice_channel_id')
    playlists = settings.get('audio_playlists', {})
    
    status_display = "🟢 Active" if is_enabled else "🔴 Inactive"
    vc_display = f"**{guild.get_channel(vc_id).name}** (`{vc_id}`)" if vc_id and guild.get_channel(vc_id) else "*Not configured*"
    playlist_display = "\n".join(f"• {name}" for name in playlists.keys()) or "*None*"

    embed.description = "Use this panel to set the music channel and manage playlists."
    embed.clear_fields()
    embed.add_field(name="System Status", value=status_display, inline=False)
    embed.add_field(name="Music Channel", value=vc_display, inline=False)
    embed.add_field(name="Saved Playlists", value=playlist_display, inline=False)
    return embed

async def _update_embed_setup_embed(cog, guild: discord.Guild, embed: discord.Embed):
    settings = await cog.config.guild(guild).all()
    named_channels = settings.get('embed_named_channels', {})
    
    channel_list = [
        f"• **{name}** -> {f'#{guild.get_channel(channel_id).name}' if guild.get_channel(channel_id) else 'Unknown Channel'} (`{channel_id}`)"
        for name, channel_id in named_channels.items()
    ]
    channel_list_display = "\n".join(channel_list) or "*No named channels configured*"
    
    embed.description = "Configure named channels to quickly send custom JSON embeds."
    embed.clear_fields()
    embed.add_field(name="Configured Channels", value=channel_list_display, inline=False)
    embed.add_field(
        name="How to Use", 
        value="1. **Set Named Channel:** Save a channel with a short name.\n"
              "2. **Send Embed:** Use the saved name and a JSON payload to send a message.", 
        inline=False
    )
    return embed

async def _update_rss_setup_embed(cog, guild: discord.Guild, embed: discord.Embed):
    settings = await cog.config.guild(guild).all()
    feeds_list = settings.get('rss_feeds', [])
    is_enabled = settings.get('rss_enabled', False)

    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    
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

async def _update_tv_setup_embed(cog, guild: discord.Guild, embed: discord.Embed):
    settings = await cog.config.guild(guild).all()
    dest_id = settings.get('tv_dest_channel')
    radarr_id = settings.get('tv_radarr_webhook_id')
    sonarr_id = settings.get('tv_sonarr_webhook_id')
    is_enabled = settings.get('tv_enabled', False)

    dest_channel = cog.bot.get_channel(dest_id)
    radarr_display = f"`{radarr_id}`" if radarr_id else "*Not configured*"
    sonarr_display = f"`{sonarr_id}`" if sonarr_id else "*Not configured*"
    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    dest_name = f"**{dest_channel.name}** (`{dest_id}`)" if dest_channel else "*Not configured*"
    
    embed.description = "Configure the refined news feed for the latest movies and TV shows."
    embed.clear_fields()
    embed.add_field(name="System Status", value=status_emoji, inline=True)
    embed.add_field(name="Radarr Integration ID", value=radarr_display, inline=False)
    embed.add_field(name="Sonarr Integration ID", value=sonarr_display, inline=False)
    embed.add_field(name="Destination Channel", value=dest_name, inline=False)
    return embed

async def _update_voice_setup_embed(cog, guild: discord.Guild, embed: discord.Embed):
    settings = await cog.config.guild(guild).all()
    source_id = settings.get('voice_source_id')
    is_enabled = settings.get('voice_enabled', False)

    source_channel = cog.bot.get_channel(source_id)
    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    source_name = f"**{source_channel.name}** (`{source_id}`)" if source_channel else "*Not configured*"
    
    embed.description = "Use this panel to set the source voice channel where new rooms are spawned."
    embed.clear_fields()
    embed.add_field(name="System Status", value=status_emoji, inline=False)
    embed.add_field(name="Source VC (Join Channel)", value=source_name, inline=False)
    return embed

async def _update_hide_setup_embed(cog, guild: discord.Guild, embed: discord.Embed):
    settings = await cog.config.guild(guild).all()
    category_id = settings.get('hide_managed_category_id')
    
    is_hidden = await cog._is_managed_category_hidden(guild) 
    status_display = "🔴 Hidden" if is_hidden else "🟢 Visible"
    category_channel = guild.get_channel(category_id)
    category_display = f"**{category_channel.name}** (`{category_id}`)" if category_channel else "*Not configured*"
    
    channel_list_str = "*None*"
    if category_channel and isinstance(category_channel, discord.CategoryChannel):
        channels = [c.mention for c in category_channel.channels if isinstance(c, (discord.TextChannel, discord.VoiceChannel))]
        channel_list_str = "\n".join(channels) if channels else "*Empty Category*"

    embed.clear_fields()
    embed.add_field(name="Visibility Status", value=status_display, inline=False)
    embed.add_field(name="Managed Category", value=category_display, inline=False)
    embed.add_field(name="Channels in Category", value=channel_list_str, inline=False)
    return embed

# --- MODALS AND VIEWS ---

# 1. AUDIO MODALS AND VIEWS

class AudioSetVoiceChannelModal(discord.ui.Modal, title="Set Music Channel"):
    channel_id_input = discord.ui.TextInput(label="Voice Channel ID", placeholder="Paste the ID of the music voice channel.", required=True)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        channel_id_str = self.channel_id_input.value.strip()
        try:
            channel_id = int(channel_id_str)
        except ValueError:
            await _send_owner_dm(self.cog.bot, f"User {interaction.user.display_name} provided invalid ID: `{channel_id_str}` in {interaction.guild.name}.")
            return await interaction.response.defer()

        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            await _send_owner_dm(self.cog.bot, f"User {interaction.user.display_name} provided an ID `{channel_id_str}` that is not a Voice Channel in {interaction.guild.name}.")
            return await interaction.response.defer()

        await self.cog.config.guild(interaction.guild).audio_music_voice_channel_id.set(channel.id)
        await interaction.response.defer(ephemeral=True)
        await self.cog.update_settings_message(interaction.guild, interaction.message)


class AudioPlayerPlayModal(discord.ui.Modal, title="Request a Song or Playlist"):
    query_input = discord.ui.TextInput(label="URL, Search, or Saved Playlist Name", placeholder="Paste a URL or type a song/playlist name.", required=True)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        query = self.query_input.value.strip()
        playlists = await self.cog.config.guild(interaction.guild).audio_playlists()
        final_query = playlists.get(query.lower(), query)
        await self.cog._invoke_audio_command(interaction, "play", query=final_query)



class AudioPlayerPlaylistSelect(discord.ui.Select):
    def __init__(self, playlists, cog):
        options = [
            discord.SelectOption(label=p["name"][:100], description="Play this playlist", value=p["url"][:100])
            for p in playlists[:25]
        ]
        if not options:
            options = [discord.SelectOption(label="No playlists available", value="none")]
        
        super().__init__(placeholder="Select a Playlist...", min_values=1, max_values=1, options=options, custom_id="audio_player_playlist_select")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No playlist selected.", ephemeral=True)
            return
        url = self.values[0]
        await self.cog._invoke_audio_command(interaction, "play", query=url)

class AudioPlayerView(discord.ui.View):
    def __init__(self, cog, is_playing: bool = False, playlists: list = None):
        super().__init__(timeout=None)
        self.cog = cog
        
        if playlists:
            self.add_item(AudioPlayerPlaylistSelect(playlists, cog))

        song_button = discord.ui.Button(label="Song", style=discord.ButtonStyle.secondary, custom_id="player_song")
        song_button.callback = self.on_song
        self.add_item(song_button)

        play_pause_button = discord.ui.Button(
            label="Pause" if is_playing else "Play",
            style=discord.ButtonStyle.secondary,
            custom_id="player_pause_toggle"
        )
        play_pause_button.callback = self.on_play_pause
        self.add_item(play_pause_button)

        skip_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="player_skip")
        skip_button.callback = self.on_skip
        self.add_item(skip_button)

        stop_button = discord.ui.Button(label="Stop", style=discord.ButtonStyle.secondary, custom_id="player_stop")
        stop_button.callback = self.on_stop
        self.add_item(stop_button)

    async def on_song(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AudioPlayerPlayModal(self.cog))

    async def on_play_pause(self, interaction: discord.Interaction):
        await self.cog._invoke_audio_command(interaction, "pause")

    async def on_skip(self, interaction: discord.Interaction):
        await self.cog._invoke_audio_command(interaction, "skip")

    async def on_stop(self, interaction: discord.Interaction):
        await self.cog._invoke_audio_command(interaction, "stop")


class AudioSettingsView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await self.cog.bot.is_owner(interaction.user):
            return True
        await _send_owner_dm(self.cog.bot, f"User {interaction.user.display_name} attempted to use owner controls in {interaction.guild.name}.")
        return False

    @discord.ui.button(label="Channel ID", style=discord.ButtonStyle.primary, custom_id="set_voice_channel")
    async def set_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AudioSetVoiceChannelModal(self.cog))


    @discord.ui.button(label="Enable/Disable", style=discord.ButtonStyle.secondary, custom_id="toggle_automation")
    async def toggle_automation_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_state = await self.cog.config.guild(interaction.guild).audio_is_enabled()
        new_state = not current_state
        await self.cog.config.guild(interaction.guild).audio_is_enabled.set(new_state)
        await self.cog.update_settings_message(interaction.guild, interaction.message)
        await interaction.response.defer()


# 2. EMBED MODALS AND VIEWS

class EmbedNamedChannelSetModal(discord.ui.Modal, title="Set or Update a Named Channel"):
    name_input = discord.ui.TextInput(label="Unique Name (e.g., 'announcements')", style=discord.TextStyle.short, required=True, max_length=50)
    channel_id_input = discord.ui.TextInput(label="Channel ID", style=discord.TextStyle.short, required=True, max_length=20)
    
    def __init__(self, cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        name = self.name_input.value.strip().lower()
        try:
            channel_id = int(self.channel_id_input.value.strip())
        except ValueError:
            return await interaction.followup.send("❌ **Error:** Channel ID must be a valid number.", ephemeral=True)
            
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send(f"❌ **Error:** Could not find a Text Channel with the ID `{channel_id}`.", ephemeral=True)

        async with self.cog.config.guild(interaction.guild).embed_named_channels() as channels:
            channels[name] = channel_id
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"Channel '{name}' updated"))
        await _update_embed_setup_embed(self.cog, interaction.guild, embed)
        await self.original_message.edit(embed=embed, view=EmbedSetupView(self.cog))


class EmbedNamedMessageSendModal(discord.ui.Modal, title="Send Embed to Named Channel"):
    name_input = discord.ui.TextInput(label="Target Saved Channel Name", style=discord.TextStyle.short, required=True, max_length=50)
    json_input = discord.ui.TextInput(label="JSON Payload (Fields, Color, etc.)", style=discord.TextStyle.long, required=True, placeholder="{\n  \"title\": \"Hello\",\n  \"description\": \"World\"\n}")
    
    def __init__(self, cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        name = self.name_input.value.strip().lower()
        json_payload = self.json_input.value.strip()
        
        named_channels = await self.cog.config.guild(interaction.guild).embed_named_channels()
        channel_id = named_channels.get(name)
        
        if not channel_id:
            return await interaction.followup.send(f"❌ **Error:** Saved channel '{name}' not found.", ephemeral=True)
            
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.followup.send("❌ **Error:** Configured channel no longer exists.", ephemeral=True)
            
        try:
            data = json.loads(json_payload)
        except json.JSONDecodeError as e:
            return await interaction.followup.send(f"❌ **Error Parsing JSON:** `{e.msg}`", ephemeral=True)
            
        embed = discord.Embed()
        if "title" in data: embed.title = data["title"]
        if "description" in data: embed.description = data["description"]
        if "color" in data:
            try: embed.color = discord.Color(int(str(data["color"]), 16))
            except ValueError: embed.color = discord.Color.blue()
        else:
            embed.color = discord.Color.blue()
            
        if "fields" in data and isinstance(data["fields"], list):
            for field in data["fields"]:
                embed.add_field(name=field.get("name", "Field"), value=field.get("value", "..."), inline=field.get("inline", False))
                
        if "thumbnail" in data: embed.set_thumbnail(url=data["thumbnail"])
        if "image" in data: embed.set_image(url=data["image"])
        
        embed.set_footer(text="e.Network | Official Announcement")
        
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return await interaction.followup.send("❌ **Error:** Lacking permission to send messages in target channel.", ephemeral=True)
            
        embed_msg = self.original_message.embeds[0]
        embed_msg.set_footer(text=_get_admin_footer(interaction, f"Embed sent to '{name}'"))
        await self.original_message.edit(embed=embed_msg)
        await interaction.followup.send("✅ Embed sent successfully.", ephemeral=True)


class EmbedSetupView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def _check_owner(self, interaction: discord.Interaction):
        if not await self.cog.bot.is_owner(interaction.user):
            await interaction.response.send_message("Only the bot owner can use this feature.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Set Channel", style=discord.ButtonStyle.primary, custom_id="embed_set_channel", row=0)
    async def set_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        await interaction.response.send_modal(EmbedNamedChannelSetModal(self.cog, interaction.message))

    @discord.ui.button(label="Send Embed", style=discord.ButtonStyle.secondary, custom_id="embed_send_msg", row=0)
    async def send_embed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        await interaction.response.send_modal(EmbedNamedMessageSendModal(self.cog, interaction.message))


# 3. RSS MODALS AND VIEWS

class RssAddFeedModal(discord.ui.Modal, title="Add New RSS Feed"):
    feed_name_input = discord.ui.TextInput(label="Feed Name (e.g., 'GitHub News')", style=discord.TextStyle.short, placeholder="A unique name to reference this feed.", required=True, max_length=50)
    channel_id_input = discord.ui.TextInput(label="Target Channel ID (Numbers Only)", style=discord.TextStyle.short, placeholder="ID of the channel to post updates in.", required=True, max_length=20)
    rss_url_input = discord.ui.TextInput(label="RSS/Atom Feed URL", style=discord.TextStyle.short, placeholder="e.g., https://github.com/red-cog/feed.xml", required=True)
    
    def __init__(self, cog, original_message: discord.Message):
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

        new_feed_data = await self.cog._add_feed_to_config(interaction.guild, feed_name, channel_id, rss_url)
        if isinstance(new_feed_data, str):
             return await interaction.followup.send(f"❌ **Error:** {new_feed_data}", ephemeral=True)

        async with self.cog.config.guild(interaction.guild).rss_feeds() as feeds:
            feeds.append(new_feed_data)

        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, "Feed added"))
        await _update_rss_setup_embed(self.cog, interaction.guild, embed)
        
        view = RssSetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).rss_enabled())
        await self.original_message.edit(embed=embed, view=view)
        await interaction.followup.send(f"✅ Feed **{feed_name}** added for {channel.mention}.", ephemeral=True)


class RssSetupView(discord.ui.View):
    def __init__(self, cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    async def _check_owner(self, interaction: discord.Interaction):
        if not await self.cog.bot.is_owner(interaction.user): 
            await interaction.response.send_message("Only the bot owner can use this feature.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Add Feed", style=discord.ButtonStyle.secondary, custom_id="rss_add_feed_button", row=0)
    async def add_feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        await interaction.response.send_modal(RssAddFeedModal(self.cog, interaction.message))

    @discord.ui.button(label="Remove Feed (Command)", style=discord.ButtonStyle.secondary, custom_id="rss_remove_feed_button", row=0, disabled=True)
    async def remove_feed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        await interaction.response.send_message("Please use the command `[p]afterwork rss remove <name>` to remove a feed.", ephemeral=True)

    @discord.ui.button(label="Toggle Status", style=discord.ButtonStyle.secondary, custom_id="rss_toggle_button", row=1)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        current_state = await self.cog.config.guild(interaction.guild).rss_enabled()
        new_state = not current_state
        await self.cog.config.guild(interaction.guild).rss_enabled.set(new_state)
        embed = interaction.message.embeds[0]
        await _update_rss_setup_embed(self.cog, interaction.guild, embed)
        view = RssSetupView(self.cog, initial_enabled=new_state)
        await interaction.response.edit_message(embed=embed, view=view)


# 4. TV MODALS AND VIEWS

class TvTargetChannelModal(discord.ui.Modal, title="Set Target Channel"):
    channel_id_input = discord.ui.TextInput(label="Target Channel ID", style=discord.TextStyle.short, placeholder="Paste the ID of the channel for clean embeds.", required=True, max_length=20)
    
    def __init__(self, cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        input_id = self.channel_id_input.value.strip()
        try: channel_id = int(input_id)
        except ValueError: return await interaction.response.send_message("❌ Invalid ID.", ephemeral=True)
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Text Channel not found.", ephemeral=True)
        
        await self.cog.config.guild(interaction.guild).tv_dest_channel.set(channel_id)
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, "Target updated"))
        await _update_tv_setup_embed(self.cog, interaction.guild, embed)
        await interaction.response.edit_message(embed=embed)


class TvRadarrIDModal(discord.ui.Modal, title="Set Radarr Integration ID"):
    user_id_input = discord.ui.TextInput(label="Radarr Integration ID", style=discord.TextStyle.short, placeholder="Paste the ID for Radarr webhooks.", required=True, max_length=20)
    
    def __init__(self, cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        input_id = self.user_id_input.value.strip()
        try: user_id = int(input_id)
        except ValueError: return await interaction.response.send_message("❌ Invalid ID.", ephemeral=True)
        
        await self.cog.config.guild(interaction.guild).tv_radarr_webhook_id.set(user_id)
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, "Radarr ID updated"))
        await _update_tv_setup_embed(self.cog, interaction.guild, embed)
        await interaction.response.edit_message(embed=embed)


class TvSonarrIDModal(discord.ui.Modal, title="Set Sonarr Integration ID"):
    user_id_input = discord.ui.TextInput(label="Sonarr Integration ID", style=discord.TextStyle.short, placeholder="Paste the ID for Sonarr webhooks.", required=True, max_length=20)
    
    def __init__(self, cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        input_id = self.user_id_input.value.strip()
        try: user_id = int(input_id)
        except ValueError: return await interaction.response.send_message("❌ Invalid ID.", ephemeral=True)
        
        await self.cog.config.guild(interaction.guild).tv_sonarr_webhook_id.set(user_id)
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, "Sonarr ID updated"))
        await _update_tv_setup_embed(self.cog, interaction.guild, embed)
        await interaction.response.edit_message(embed=embed)


class TvSetupView(discord.ui.View):
    def __init__(self, cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    @discord.ui.button(label="Target Channel", style=discord.ButtonStyle.primary, custom_id="tv_set_target", row=0)
    async def set_target_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        await interaction.response.send_modal(TvTargetChannelModal(self.cog, interaction.message))

    @discord.ui.button(label="Radarr ID", style=discord.ButtonStyle.secondary, custom_id="tv_set_radarr", row=0)
    async def set_radarr_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        await interaction.response.send_modal(TvRadarrIDModal(self.cog, interaction.message))

    @discord.ui.button(label="Sonarr ID", style=discord.ButtonStyle.secondary, custom_id="tv_set_sonarr", row=0)
    async def set_sonarr_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        await interaction.response.send_modal(TvSonarrIDModal(self.cog, interaction.message))

    @discord.ui.button(label="Enable/Disable", style=discord.ButtonStyle.secondary, custom_id="tv_toggle_system", row=1)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        new_state = not (await self.cog.config.guild(interaction.guild).tv_enabled())
        await self.cog.config.guild(interaction.guild).tv_enabled.set(new_state)
        
        button.label = "Disable" if new_state else "Enable"
        button.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success
        
        embed = interaction.message.embeds[0]
        status_msg = f"System {'enabled' if new_state else 'disabled'}"
        embed.set_footer(text=_get_admin_footer(interaction, status_msg))
        
        await _update_tv_setup_embed(self.cog, interaction.guild, embed)
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send(f"System has been **{'enabled' if new_state else 'disabled'}**.", ephemeral=True)


# 5. VOICE MODALS AND VIEWS

class VoiceChannelIDModal(discord.ui.Modal, title="Set Source Voice Channel"):
    channel_id_input = discord.ui.TextInput(label="Voice Channel ID (Numbers Only)", style=discord.TextStyle.short, placeholder="Paste the ID of the VC you want to use as the source.", required=True, max_length=20)
    
    def __init__(self, cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        input_id = self.channel_id_input.value.strip()
        try: channel_id = int(input_id)
        except ValueError:
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. User: {interaction.user.display_name}. Configuration failed: Invalid Channel ID input (`{input_id}`).")
            return await interaction.response.defer()
        
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. User: {interaction.user.display_name}. Configuration failed: ID `{channel_id}` is not a valid Voice Channel.")
            return await interaction.response.defer()
        
        await self.cog.config.guild(interaction.guild).voice_source_id.set(channel_id)
        await self.cog.config.guild(interaction.guild).voice_enabled.set(True)
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, "Source ID updated"))
        await _update_voice_setup_embed(self.cog, interaction.guild, embed)
        
        view = VoiceSetupView(self.cog, initial_enabled=True)
        await interaction.response.edit_message(embed=embed, view=view)


class VoiceSetupView(discord.ui.View):
    def __init__(self, cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    @discord.ui.button(label="Channel ID", style=discord.ButtonStyle.primary, custom_id="voice_set_button", row=0)
    async def set_source_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Unauthorized access: User {interaction.user.display_name} attempted to use owner controls.")
            return await interaction.response.defer()
        await interaction.response.send_modal(VoiceChannelIDModal(self.cog, interaction.message))

    @discord.ui.button(label="Enable/Disable", style=discord.ButtonStyle.secondary, custom_id="voice_toggle_button", row=0)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Unauthorized access: User {interaction.user.display_name} attempted to use owner controls.")
            return await interaction.response.defer()
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        new_state = not (await self.cog.config.guild(interaction.guild).voice_enabled())
        await self.cog.config.guild(interaction.guild).voice_enabled.set(new_state)
        
        button.label = "Disable" if new_state else "Enable"
        button.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success
        
        embed = interaction.message.embeds[0]
        status_msg = f"System {'enabled' if new_state else 'disabled'}"
        embed.set_footer(text=_get_admin_footer(interaction, status_msg))
        
        await _update_voice_setup_embed(self.cog, interaction.guild, embed)
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.defer()


class VoiceChannelButtons(discord.ui.View):
    def __init__(self, cog, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=None)
        self.cog = cog
        self.voice_channel = voice_channel
        self.selected_member_id = None
        self.member_select = discord.ui.Select(placeholder="Select a member to manage...", custom_id="voice_member_select", options=[discord.SelectOption(label="Refreshing...", value="none")])
        self.kick_button = discord.ui.Button(label="Kick", style=discord.ButtonStyle.secondary, custom_id="voice_kick", disabled=True)
        self.transfer_button = discord.ui.Button(label="Transfer", style=discord.ButtonStyle.secondary, custom_id="voice_transfer", disabled=True)
        self.refresh_button = discord.ui.Button(label="Refresh", style=discord.ButtonStyle.secondary, custom_id="voice_refresh")
        self.privacy_button = discord.ui.Button(label="Make Private", style=discord.ButtonStyle.secondary, custom_id="voice_privacy_toggle")
        
        self.add_item(self.member_select)
        self.add_item(self.kick_button)
        self.add_item(self.transfer_button)
        self.add_item(self.refresh_button)
        self.add_item(self.privacy_button)
        
        self.member_select.callback = self.on_member_select
        self.kick_button.callback = self.on_kick
        self.transfer_button.callback = self.on_transfer
        self.refresh_button.callback = self.on_refresh
        self.privacy_button.callback = self.on_privacy_toggle
        
    @classmethod
    async def create(cls, cog, voice_channel: discord.VoiceChannel):
        view = cls(cog, voice_channel)
        await view._update_member_options()
        return view

    async def _update_member_options(self):
        vc = self.cog.bot.get_channel(self.voice_channel.id)
        if not vc:
            self.member_select.options = [discord.SelectOption(label="Channel not found", value="none")]
            return
        async with self.cog.config.guild(vc.guild).voice_room_channels() as rooms:
            owner_id = rooms.get(str(vc.id), {}).get("owner_id")
        options = [discord.SelectOption(label=member.display_name, value=str(member.id)) for member in vc.members if member.id != owner_id]
        if not options:
            self.member_select.options = [discord.SelectOption(label="No other members in channel", value="none")]
            self.member_select.disabled = True
        else:
            self.member_select.options = options
            self.member_select.disabled = False

    async def _check_owner(self, interaction: discord.Interaction) -> bool:
        if not self.voice_channel:
             await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Error: Could not determine target voice channel during interaction check.")
             await interaction.response.defer()
             return False
        async with self.cog.config.guild(interaction.guild).voice_room_channels() as room_channels:
            room_data = room_channels.get(str(self.voice_channel.id))
            if not room_data or room_data.get("owner_id") != interaction.user.id:
                await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Room: {self.voice_channel.name}. User: {interaction.user.display_name} is not the room owner and tried to use controls.")
                await interaction.response.defer()
                return False
        return True

    async def on_member_select(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction): return
        selection = interaction.data.get("values")
        if not selection or selection[0] == "none":
            self.selected_member_id = None
            self.kick_button.disabled = True
            self.transfer_button.disabled = True
            self.member_select.placeholder = "Select a member to manage..."
        else:
            self.selected_member_id = int(selection[0])
            member = interaction.guild.get_member(self.selected_member_id)
            self.member_select.placeholder = f"Selected: {member.display_name}" if member else "Select a member to manage..."
            self.kick_button.disabled = False
            self.transfer_button.disabled = False
        await interaction.response.edit_message(view=self)

    async def on_kick(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction) or not self.selected_member_id:
            return
        member_to_kick = interaction.guild.get_member(self.selected_member_id)
        if not member_to_kick:
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Room: {self.voice_channel.name}. Error: Member with ID {self.selected_member_id} not found during kick attempt.")
            return await interaction.response.defer()
            
        try:
            await member_to_kick.move_to(None, reason=f"Kicked by room owner {interaction.user.name}")
            await interaction.response.defer()
        except discord.Forbidden:
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Room: {self.voice_channel.name}. Error: Bot lacks permission to kick {member_to_kick.display_name}.")
            return await interaction.response.defer()
        
        await self._update_member_options()
        self.kick_button.disabled = True
        self.transfer_button.disabled = True
        self.selected_member_id = None
        await interaction.message.edit(view=self)

    async def on_transfer(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction) or not self.selected_member_id:
            return
        new_owner = interaction.guild.get_member(self.selected_member_id)
        if not new_owner:
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Room: {self.voice_channel.name}. Error: New owner with ID {self.selected_member_id} not found during transfer attempt.")
            return await interaction.response.defer()
            
        async with self.cog.config.guild(interaction.guild).voice_room_channels() as room_channels:
            room_data = room_channels.get(str(self.voice_channel.id))
            if not room_data:
                await interaction.response.defer()
                return
            room_data["owner_id"] = new_owner.id
            
        original_embed = interaction.message.embeds[0]
        original_embed.set_field_at(0, name="Current Owner", value=new_owner.mention, inline=False)
        
        await interaction.response.defer()
        await self._update_member_options()
        self.kick_button.disabled = True
        self.transfer_button.disabled = True
        self.selected_member_id = None
        await interaction.message.edit(embed=original_embed, view=self)
        
    async def on_refresh(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction): return
        await interaction.response.defer()
        await self._update_member_options()
        await interaction.message.edit(view=self)

    async def on_privacy_toggle(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction): return
        overwrites = self.voice_channel.overwrites_for(interaction.guild.default_role)
        is_public = overwrites.connect is not False
        try:
            if is_public:
                overwrites.connect = False
                await self.voice_channel.set_permissions(interaction.guild.default_role, overwrite=overwrites)
                for member in self.voice_channel.members:
                    await self.voice_channel.set_permissions(member, connect=True)
                self.privacy_button.label = "Make Public"
                self.privacy_button.style = discord.ButtonStyle.success
            else:
                overwrites.connect = None
                await self.voice_channel.set_permissions(interaction.guild.default_role, overwrite=overwrites)
                self.privacy_button.label = "Make Private"
                self.privacy_button.style = discord.ButtonStyle.secondary
            
            await interaction.response.edit_message(view=self)
        except discord.Forbidden:
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Room: {self.voice_channel.name}. Error: Bot lacks permission to change channel privacy.")
            return await interaction.response.defer()


# 6. HIDE MODALS AND VIEWS

class HideCategoryIDModal(discord.ui.Modal, title="Set Managed Category ID"):
    category_id_input = discord.ui.TextInput(label="Category ID", style=discord.TextStyle.short, placeholder="Paste the ID of the channel category to manage.", required=True, max_length=20)

    def __init__(self, cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        input_id = self.category_id_input.value.strip()
        try: category_id = int(input_id)
        except ValueError: 
            return await interaction.followup.send("❌ **Error:** Input must be a valid Category ID.")
        
        category = interaction.guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            return await interaction.followup.send(f"❌ **Error:** Could not find a Category Channel with the ID `{category_id}`.")

        await self.cog.config.guild(interaction.guild).hide_managed_category_id.set(category_id)
        await interaction.followup.send(f"✅ Managed Category set to **{category.name}**.", ephemeral=True)
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, "Category updated"))
        await _update_hide_setup_embed(self.cog, interaction.guild, embed)
        
        initial_hidden = await self.cog._is_managed_category_hidden(interaction.guild)
        view = HideSetupView(self.cog, initial_hidden=initial_hidden) 
        await self.original_message.edit(embed=embed, view=view)


class HideSetupView(discord.ui.View):
    def __init__(self, cog, initial_hidden: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.toggle_visibility_action.label = "Show" if initial_hidden else "Hide"
        self.toggle_visibility_action.style = discord.ButtonStyle.success if initial_hidden else discord.ButtonStyle.danger

    @discord.ui.button(label="Category ID", style=discord.ButtonStyle.primary, custom_id="hide_set_category_button", row=0)
    async def set_category_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=False)
        await interaction.response.send_modal(HideCategoryIDModal(self.cog, interaction.message))

    @discord.ui.button(label="Hide / Show", style=discord.ButtonStyle.secondary, custom_id="hide_show_button", row=0)
    async def toggle_visibility_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=False)
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        settings = await self.cog.config.guild(interaction.guild).all()
        category_id = settings.get('hide_managed_category_id')
        category = interaction.guild.get_channel(category_id)
        
        if not category or not isinstance(category, discord.CategoryChannel):
            return await interaction.followup.send("❌ **Error:** No category is configured.")

        is_currently_hidden = await self.cog._is_managed_category_hidden(interaction.guild)
        perm_action = None
        
        if is_currently_hidden: 
            action_verb = "shown (unhidden)"
            perm_action = lambda target, role, reason: target.set_permissions(role, view_channel=None, reason=reason)
            new_button_label = "Hide"
            new_button_style = discord.ButtonStyle.danger
        else: 
            action_verb = "hidden"
            perm_action = lambda target, role, reason: target.set_permissions(role, view_channel=False, reason=reason)
            new_button_label = "Show"
            new_button_style = discord.ButtonStyle.success
        
        await self.cog._apply_perms_to_category(interaction.guild, perm_action)
        
        button.label = new_button_label
        button.style = new_button_style
        
        embed = interaction.message.embeds[0]
        status_msg = f"Channels were {action_verb}"
        embed.set_footer(text=_get_admin_footer(interaction, status_msg))
        
        await _update_hide_setup_embed(self.cog, interaction.guild, embed)
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send(f"Managed channels have been **{action_verb}** for admins.", ephemeral=True)


# === MAIN COG CLASS ===

class Afterwork(commands.Cog, name="Afterwork"):
    """Unified administrative control hub for Afterwork server management."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1122334455, force_registration=True)
        self.config.register_guild(
            # Audio
            audio_music_voice_channel_id=None,
            audio_settings_message_id=None,
            audio_player_message_id=None,
            audio_is_enabled=False,
            audio_playlists={},

            # Embed
            embed_setup_message_id=None,
            embed_named_channels={},

            # RSS
            rss_enabled=False,
            rss_setup_message_id=None,
            rss_feeds=[],

            # TV
            tv_enabled=False,
            tv_setup_message_id=None,
            tv_dest_channel=None,
            tv_radarr_webhook_id=None,
            tv_sonarr_webhook_id=None,

            # Voice
            voice_enabled=False,
            voice_setup_message_id=None,
            voice_source_id=None,
            voice_room_channels={},

            # Hide
            hide_setup_message_id=None,
            hide_managed_category_id=None,
            # Member
            member_setup_message_id=None,
            member_base_role_id=None,
            member_ark_role_id=None,
            member_dune_role_id=None,
            # Repost
            repost_setup_message_id=None,
            repost_enabled=True,
            repost_channels={},
            repost_last_news_id=0,
            repost_last_events_id=0,
            # Discord
            discord_setup_message_id=None,
            discord_enabled=True,
            discord_channels={},
            discord_last_embeds_ids={},
            discord_last_news_ids={},
            discord_last_events_ids={},
        )

        self.config.register_global(
            web_server_host="0.0.0.0",
            web_server_port=9000,
            web_server_token="afterwork-secret-token"
        )

        self.settings_view = AudioSettingsView(self)
        self.player_view = AudioPlayerView(self)
        self.update_tasks = {}

        self._read_feeds_loop = None
        self._headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"}
        self._post_queue = asyncio.Queue()

        self.web_app = None
        self.web_runner = None
        self.web_site = None

    async def initialize(self):
        self.bot.add_view(self.settings_view)
        self.bot.add_view(self.player_view)

        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            guild = self.bot.get_guild(guild_id)
            
            if data.get('embed_setup_message_id'):
                self.bot.add_view(EmbedSetupView(self), message_id=data['embed_setup_message_id'])

            if data.get('rss_setup_message_id'):
                self.bot.add_view(RssSetupView(self, initial_enabled=data.get('rss_enabled', False)), message_id=data['rss_setup_message_id'])

            if data.get('tv_setup_message_id'):
                self.bot.add_view(TvSetupView(self, initial_enabled=data.get('tv_enabled', False)), message_id=data['tv_setup_message_id'])

            if data.get('voice_setup_message_id'):
                self.bot.add_view(VoiceSetupView(self, initial_enabled=data.get('voice_enabled', False)), message_id=data['voice_setup_message_id'])

            if data.get('hide_setup_message_id') and guild:
                initial_hidden = await self._is_managed_category_hidden(guild)
                self.bot.add_view(HideSetupView(self, initial_hidden=initial_hidden), message_id=data['hide_setup_message_id'])

            if data.get('repost_setup_message_id'):
                self.bot.add_view(RepostSetupView(self), message_id=data['repost_setup_message_id'])

            if data.get('discord_setup_message_id'):
                self.bot.add_view(DiscordSetupView(self), message_id=data['discord_setup_message_id'])

        self.start_background_loop()
        await self.start_web_server()

    def start_background_loop(self):
        if not self._read_feeds_loop:
            self._read_feeds_loop = self.bot.loop.create_task(self.read_feeds())
        if not hasattr(self, '_repost_loop') or not self._repost_loop:
            self._repost_loop = self.bot.loop.create_task(self.repost_polling_task())
        if not hasattr(self, '_discord_loop') or not self._discord_loop:
            self._discord_loop = self.bot.loop.create_task(self.discord_polling_task())

    def cog_unload(self):
        if hasattr(self, '_repost_loop') and self._repost_loop:
            self._repost_loop.cancel()
        if hasattr(self, '_discord_loop') and self._discord_loop:
            self._discord_loop.cancel()
        for task in self.update_tasks.values():
            task.cancel()
        if self._read_feeds_loop:
            self._read_feeds_loop.cancel()
        if self.web_app:
            self.bot.loop.create_task(self.stop_web_server())

    # --- HTTP REST API SERVER ---

    async def start_web_server(self):
        from aiohttp import web
        host = await self.config.web_server_host()
        port = await self.config.web_server_port()

        self.web_app = web.Application()
        self.web_app.router.add_get("/api/v1/channels", self.handle_get_channels)
        self.web_app.router.add_post("/api/v1/embed", self.handle_post_embed)

        self.web_runner = web.AppRunner(self.web_app)
        await self.web_runner.setup()

        self.web_site = web.TCPSite(self.web_runner, host, port)
        try:
            await self.web_site.start()
            log.info(f"Afterwork HTTP server started on {host}:{port}")
        except Exception as e:
            log.error(f"Failed to start Afterwork HTTP server: {e}")

    async def stop_web_server(self):
        if self.web_site:
            await self.web_site.stop()
            self.web_site = None
        if self.web_runner:
            await self.web_runner.cleanup()
            self.web_runner = None
        self.web_app = None
        log.info("Afterwork HTTP server stopped.")

    async def handle_get_channels(self, request):
        from aiohttp import web
        token = request.headers.get("Authorization")
        expected_token = f"Bearer {await self.config.web_server_token()}"
        if token != expected_token:
            return web.json_response({"error": "Unauthorized"}, status=401)

        guild_id_str = request.query.get("guild_id")
        guild = None
        if guild_id_str:
            try:
                guild = self.bot.get_guild(int(guild_id_str))
            except ValueError:
                pass
        if not guild and self.bot.guilds:
            guild = self.bot.guilds[0]

        if not guild:
            return web.json_response({"error": "No guilds found"}, status=404)

        channels = []
        for chan in guild.text_channels:
            channels.append({
                "id": str(chan.id),
                "name": chan.name
            })
        return web.json_response({"channels": channels})

    async def handle_post_embed(self, request):
        from aiohttp import web
        token = request.headers.get("Authorization")
        expected_token = f"Bearer {await self.config.web_server_token()}"
        if token != expected_token:
            return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON payload"}, status=400)

        channel_id_str = data.get("channel_id")
        embed_data = data.get("embed")

        if not channel_id_str or not embed_data:
            return web.json_response({"error": "Missing channel_id or embed data"}, status=400)

        try:
            channel_id = int(channel_id_str)
        except ValueError:
            return web.json_response({"error": "Invalid channel_id format"}, status=400)

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return web.json_response({"error": "Channel not found"}, status=404)

        try:
            embed = discord.Embed.from_dict(embed_data)
        except Exception as e:
            return web.json_response({"error": f"Invalid embed structure: {str(e)}"}, status=400)

        try:
            message = await channel.send(embed=embed)
            return web.json_response({"status": "success", "message_id": str(message.id)})
        except Exception as e:
            return web.json_response({"error": f"Failed to send message: {str(e)}"}, status=500)

    # --- MAIN COMMAND GROUP ---

    # --- MAIN COMMAND GROUP & STATUS DASHBOARD ---

    @commands.group(name="afterwork", invoke_without_command=True)
    @commands.is_owner()
    async def afterwork_group(self, ctx: commands.Context):
        """Central configuration and status hub for Afterwork server management."""
        if ctx.invoked_subcommand is None:
            await self.show_status_dashboard(ctx)

    async def show_status_dashboard(self, ctx: commands.Context):
        """Displays a summary dashboard of all Afterwork modules and their statuses."""
        settings = await self.config.guild(ctx.guild).all()
        embed_color = await ctx.embed_color()
        
        embed = discord.Embed(
            title="📊 Afterwork System Status Dashboard",
            description="Current status and configuration summary for all integrated modules.",
            color=embed_color
        )
        
        # 1. Audio
        audio_enabled = settings.get('audio_is_enabled', False)
        audio_status = "🟢 Active" if audio_enabled else "🔴 Inactive"
        audio_vc = settings.get('audio_music_voice_channel_id')
        audio_vc_name = ctx.guild.get_channel(audio_vc).name if audio_vc and ctx.guild.get_channel(audio_vc) else "Not set"
        playlists_count = len(settings.get('audio_playlists', {}))
        embed.add_field(
            name="🎵 Audio Module",
            value=f"**Status:** {audio_status}\n**VC:** `{audio_vc_name}`\n**Playlists:** {playlists_count}",
            inline=True
        )

        # 2. Embed
        embed_channels = len(settings.get('embed_named_channels', {}))
        embed.add_field(
            name="📝 Embed Module",
            value=f"**Status:** 🟢 Active\n**Named Channels:** {embed_channels}",
            inline=True
        )

        # 3. RSS
        rss_enabled = settings.get('rss_enabled', False)
        rss_status = "🟢 Active" if rss_enabled else "🔴 Inactive"
        rss_feeds_count = len(settings.get('rss_feeds', []))
        embed.add_field(
            name="📰 RSS Module",
            value=f"**Status:** {rss_status}\n**Monitored Feeds:** {rss_feeds_count}",
            inline=True
        )

        # 4. TV
        tv_enabled = settings.get('tv_enabled', False)
        tv_status = "🟢 Active" if tv_enabled else "🔴 Inactive"
        tv_dest = settings.get('tv_dest_channel')
        tv_dest_name = ctx.guild.get_channel(tv_dest).name if tv_dest and ctx.guild.get_channel(tv_dest) else "Not set"
        embed.add_field(
            name="📺 TV Module",
            value=f"**Status:** {tv_status}\n**Dest Channel:** `{tv_dest_name}`",
            inline=True
        )

        # 5. Voice
        voice_enabled = settings.get('voice_enabled', False)
        voice_status = "🟢 Active" if voice_enabled else "🔴 Inactive"
        voice_src = settings.get('voice_source_id')
        voice_src_name = ctx.guild.get_channel(voice_src).name if voice_src and ctx.guild.get_channel(voice_src) else "Not set"
        active_rooms = len(settings.get('voice_room_channels', {}))
        embed.add_field(
            name="🔊 Voice Module",
            value=f"**Status:** {voice_status}\n**Source VC:** `{voice_src_name}`\n**Active Rooms:** {active_rooms}",
            inline=True
        )

        # 6. Hide
        hide_category = settings.get('hide_managed_category_id')
        hide_cat_name = ctx.guild.get_channel(hide_category).name if hide_category and ctx.guild.get_channel(hide_category) else "Not set"
        is_hidden = await self._is_managed_category_hidden(ctx.guild)
        hide_status = "🔴 Hidden" if is_hidden else "🟢 Visible"
        embed.add_field(
            name="🔒 Hide Module",
            value=f"**Visibility:** {hide_status}\n**Category:** `{hide_cat_name}`",
            inline=True
        )

        embed.set_footer(text=f"e.Network | Checked by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @afterwork_group.command(name="help")
    async def afterwork_help(self, ctx: commands.Context):
        """List all available subcommands for Afterwork."""
        await ctx.send_help(self.afterwork_group)

    # --- DEPLOY SUBCOMMAND GROUP ---

    @afterwork_group.group(name="deploy", invoke_without_command=True)
    @commands.is_owner()
    async def afterwork_deploy_group(self, ctx: commands.Context):
        """Deploys one or all configuration hubs.
        
        Typing this without subcommands deploys all hubs sequentially.
        """
        if ctx.invoked_subcommand is None:
            await self.deploy_all(ctx)

    @afterwork_deploy_group.command(name="audio")
    @commands.is_owner()
    async def afterwork_audio_deploy_cmd(self, ctx: commands.Context):
        """Deploys the persistent settings panel for Audio."""
        await self.afterwork_audio_deploy(ctx)

    @afterwork_deploy_group.command(name="rss")
    @commands.is_owner()
    async def afterwork_rss_deploy_cmd(self, ctx: commands.Context):
        """Deploys the persistent settings panel for RSS."""
        await self.afterwork_rss_deploy(ctx)

    @afterwork_deploy_group.command(name="tv")
    @commands.is_owner()
    async def afterwork_tv_deploy_cmd(self, ctx: commands.Context):
        """Deploys the persistent settings panel for TV."""
        await self.afterwork_tv_deploy(ctx)

    @afterwork_deploy_group.command(name="voice")
    @commands.is_owner()
    async def afterwork_voice_deploy_cmd(self, ctx: commands.Context):
        """Deploys the persistent settings panel for Voice."""
        await self.afterwork_voice_deploy(ctx)

    @afterwork_deploy_group.command(name="hide")
    @commands.is_owner()
    async def afterwork_hide_deploy_cmd(self, ctx: commands.Context):
        """Deploys the persistent settings panel for Hide Category Visibility."""
        await self.afterwork_hide_deploy(ctx)

    @afterwork_deploy_group.command(name="discord")
    @commands.is_owner()
    async def afterwork_discord_deploy_cmd(self, ctx: commands.Context):
        """Deploys the persistent settings panel for Discord Embed Manager."""
        await self.afterwork_discord_deploy(ctx)


    # --- RSS SUBCOMMAND GROUP ---

    @afterwork_group.group(name="rss")
    async def afterwork_rss_group(self, ctx: commands.Context):
        """RSS feed management commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @afterwork_rss_group.command(name="add")
    async def afterwork_rss_add(self, ctx: commands.Context, feed_name: str, channel: Union[discord.TextChannel, discord.Thread], url: str):
        """Adds a new RSS feed subscription to a channel."""
        feed_name = feed_name.lower().strip()
        
        if not channel.permissions_for(ctx.guild.me).send_messages:
             return await ctx.send(f"❌ **Error:** I do not have permission to post messages in {channel.mention}.")

        await ctx.typing()
        new_feed_data = await self._add_feed_to_config(ctx.guild, feed_name, channel.id, url)
        if isinstance(new_feed_data, str):
             return await ctx.send(f"❌ **Error:** {new_feed_data}")

        async with self.config.guild(ctx.guild).rss_feeds() as feeds:
            feeds.append(new_feed_data)

        # Update setup panel embed if it exists
        setup_message_id = await self.config.guild(ctx.guild).rss_setup_message_id()
        if setup_message_id:
            for ch in ctx.guild.text_channels:
                try:
                    msg = await ch.fetch_message(setup_message_id)
                    embed = msg.embeds[0]
                    embed.set_footer(text=_get_admin_footer(ctx, "Feed added (Command)"))
                    await _update_rss_setup_embed(self, ctx.guild, embed)
                    view = RssSetupView(self, initial_enabled=await self.config.guild(ctx.guild).rss_enabled())
                    await msg.edit(embed=embed, view=view)
                    break
                except Exception:
                    continue

        await ctx.send(f"✅ Feed **{feed_name}** added successfully for {channel.mention}!")

    @afterwork_rss_group.command(name="remove")
    async def afterwork_rss_remove(self, ctx, feed_name: str):
        """Removes an RSS feed by its configured name."""
        feed_name = feed_name.lower()
        async with self.config.guild(ctx.guild).rss_feeds() as feeds:
            initial_len = len(feeds)
            feeds[:] = [f for f in feeds if f['name'] != feed_name]
            
            if len(feeds) < initial_len:
                # Update setup panel embed if it exists
                setup_message_id = await self.config.guild(ctx.guild).rss_setup_message_id()
                if setup_message_id:
                    for ch in ctx.guild.text_channels:
                        try:
                            msg = await ch.fetch_message(setup_message_id)
                            embed = msg.embeds[0]
                            embed.set_footer(text=_get_admin_footer(ctx, "Feed removed (Command)"))
                            await _update_rss_setup_embed(self, ctx.guild, embed)
                            view = RssSetupView(self, initial_enabled=await self.config.guild(ctx.guild).rss_enabled())
                            await msg.edit(embed=embed, view=view)
                            break
                        except Exception:
                            continue
                await ctx.send(f"✅ Feed **{feed_name}** removed.")
            else:
                await ctx.send(f"❌ Feed **{feed_name}** not found.")

    # --- RESET SUBCOMMAND GROUP ---
    
    @afterwork_group.group(name="reset", invoke_without_command=True)
    async def afterwork_reset_group(self, ctx: commands.Context):
        """Reset configuration hubs."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @afterwork_reset_group.command(name="audio")
    async def afterwork_reset_audio_cmd(self, ctx: commands.Context):
        """Clears all audio settings (playlists, channel id, etc.)."""
        await self.config.guild(ctx.guild).audio_playlists.set({})
        await self.config.guild(ctx.guild).audio_music_voice_channel_id.set(None)
        await self.config.guild(ctx.guild).audio_is_enabled.set(False)
        await ctx.send("✅ Audio configuration has been fully reset (playlists and channel bindings cleared).")

    # === Main Deploy All Command ===
    async def deploy_all(self, ctx: commands.Context):
        """Deploys all configuration hubs sequentially in the channel."""
        bot_member = ctx.guild.me
        perms = ctx.channel.permissions_for(bot_member)
        if not perms.send_messages or not perms.manage_messages:
            return await _send_owner_dm(self.bot, f"Deploy failed in **{ctx.guild.name}**. Need Send/Manage Messages in **#{ctx.channel.name}**.")

        deploy_msg = await ctx.send("⌛ **Deploying all Afterwork configuration hubs...**")
        
        subcommands = [
            self.afterwork_audio_deploy,
            self.afterwork_rss_deploy,
            self.afterwork_tv_deploy,
            self.afterwork_voice_deploy,
            self.afterwork_hide_deploy,
            self.afterwork_discord_deploy
        ]
        
        for sub_cmd in subcommands:
            try:
                await sub_cmd(ctx)
                await asyncio.sleep(1.5)
            except Exception as e:
                log.error(f"Error deploying submodule: {e}", exc_info=True)
                await ctx.send(f"⚠️ Error deploying submodule: {e.__class__.__name__}")

        try:
            await deploy_msg.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

    # --- DEPLOYMENT HELPER METHODS ---

    async def afterwork_audio_deploy(self, ctx: commands.Context):
        """Deploys the persistent settings panel for Audio."""
        old_message_id = await self.config.guild(ctx.guild).audio_settings_message_id()
        if old_message_id:
            try:
                old_msg = await ctx.channel.fetch_message(old_message_id)
                await old_msg.delete()
            except (discord.NotFound, discord.Forbidden): pass

        settings = await self.config.guild(ctx.guild).all()
        is_enabled = settings.get('audio_is_enabled', False)
        vc_id = settings.get('audio_music_voice_channel_id')
        playlists = settings.get('audio_playlists', {})
        
        status_display = "🟢 Active" if is_enabled else "🔴 Inactive"
        vc_display = f"**{ctx.guild.get_channel(vc_id).name}** (`{vc_id}`)" if vc_id and ctx.guild.get_channel(vc_id) else "*Not configured*"
        playlist_display = "\n".join(f"• {name}" for name in playlists.keys()) or "*None*"

        embed = discord.Embed(
            title="Audio Setup",
            description="Use this panel to set the music channel and manage playlists.",
            color=discord.Color.purple()
        )
        embed.add_field(name="System Status", value=status_display, inline=False)
        embed.add_field(name="Music Channel", value=vc_display, inline=False)
        embed.add_field(name="Saved Playlists", value=playlist_display, inline=False)
        embed.set_footer(text=_get_admin_footer(ctx, "Configuration Hub Deployed"))
        
        toggle_button = discord.utils.get(self.settings_view.children, custom_id="toggle_automation")
        if toggle_button:
            if is_enabled:
                toggle_button.label = "Disable"
                toggle_button.style = discord.ButtonStyle.danger
            else:
                toggle_button.label = "Enable"
                toggle_button.style = discord.ButtonStyle.success

        msg = await ctx.send(embed=embed, view=self.settings_view)
        await self.config.guild(ctx.guild).audio_settings_message_id.set(msg.id)
        
        try: await msg.pin(reason="Afterwork Audio Control Panel")
        except discord.Forbidden: pass
        
        try: await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden): pass
        
        await asyncio.sleep(1)
        try:
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception: pass

    async def afterwork_rss_deploy(self, ctx: commands.Context):
        """Deploys the persistent settings panel for RSS."""
        old_message_id = await self.config.guild(ctx.guild).rss_setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException: pass
            
        initial_embed = discord.Embed(title="RSS Feed Setup", description="Loading...", color=discord.Color.purple())
        initial_embed = await _update_rss_setup_embed(self, ctx.guild, initial_embed)
        initial_embed.set_footer(text=_get_admin_footer(ctx, "Configuration Hub Deployed"))
        initial_enabled = await self.config.guild(ctx.guild).rss_enabled()
        
        view = RssSetupView(self, initial_enabled=initial_enabled)
        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        await sent_message.pin(reason="Afterwork RSS Configuration Hub.")
        await self.config.guild(ctx.guild).rss_setup_message_id.set(sent_message.id)
        
        try: await ctx.message.delete()
        except discord.HTTPException: pass
        await asyncio.sleep(1)
        try:
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception: pass

    async def afterwork_tv_deploy(self, ctx: commands.Context):
        """Deploys the persistent settings panel for TV."""
        old_message_id = await self.config.guild(ctx.guild).tv_setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException: pass

        initial_embed = discord.Embed(title="Radarr and Sonarr Setup", description="Loading...", color=discord.Color.purple())
        initial_embed.set_footer(text=_get_admin_footer(ctx, "Configuration Hub Deployed"))
        initial_embed = await _update_tv_setup_embed(self, ctx.guild, initial_embed)
        initial_enabled = await self.config.guild(ctx.guild).tv_enabled()

        view = TvSetupView(self, initial_enabled=initial_enabled)
        sent_message = await ctx.send(embed=initial_embed, view=view)

        await sent_message.pin(reason="Afterwork TV Configuration Hub.")
        await self.config.guild(ctx.guild).tv_setup_message_id.set(sent_message.id)

        try: await ctx.message.delete()
        except discord.HTTPException: pass
        await asyncio.sleep(1)
        try:
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception: pass

    async def afterwork_voice_deploy(self, ctx: commands.Context):
        """Deploys the persistent settings panel for Voice."""
        old_message_id = await self.config.guild(ctx.guild).voice_setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException: pass

        initial_embed = discord.Embed(title="Voice Channel Setup", description="Loading...", color=discord.Color.purple())
        initial_embed = await _update_voice_setup_embed(self, ctx.guild, initial_embed)
        initial_enabled = await self.config.guild(ctx.guild).voice_enabled()
        
        view = VoiceSetupView(self, initial_enabled=initial_enabled)
        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        await sent_message.pin(reason="Afterwork Voice Configuration Hub.")
        await self.config.guild(ctx.guild).voice_setup_message_id.set(sent_message.id)
        
        try: await ctx.message.delete()
        except discord.HTTPException: pass
        await asyncio.sleep(1)
        try:
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception: pass

    async def afterwork_discord_deploy(self, ctx: commands.Context):
        """Deploys the persistent settings panel for Discord Embed Manager."""
        old_message_id = await self.config.guild(ctx.guild).discord_setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except Exception: pass

        embed = discord.Embed(title="Discord Embed Manager Setup", description="Loading...", color=discord.Color.purple())
        await _update_discord_setup_embed(self, ctx.guild, embed)
        
        msg = await ctx.send(embed=embed, view=DiscordSetupView(self))
        await self.config.guild(ctx.guild).discord_setup_message_id.set(msg.id)

    async def afterwork_hide_deploy(self, ctx: commands.Context):
        """Deploys the persistent settings panel for Hide Category Visibility."""
        old_message_id = await self.config.guild(ctx.guild).hide_setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException: pass

        initial_hidden = await self._is_managed_category_hidden(ctx.guild)
        description = (
            "This tool manages the visibility of channels within a configured category. "
            "Hidden from roles with Administrator or Manage Channels permissions."
        )
        initial_embed = discord.Embed(title="Hidden Channel Setup", description=description, color=discord.Color.purple())
        initial_embed = await _update_hide_setup_embed(self, ctx.guild, initial_embed)
        initial_embed.set_footer(text=_get_admin_footer(ctx, "Configuration Hub Deployed"))
        
        view = HideSetupView(self, initial_hidden=initial_hidden) 
        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        await sent_message.pin(reason="Afterwork Hide Configuration Hub.")
        await self.config.guild(ctx.guild).hide_setup_message_id.set(sent_message.id)
        
        try: await ctx.message.delete()
        except discord.HTTPException: pass
        await asyncio.sleep(1)
        try:
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception: pass

    # --- AUDIO CORE METHODS & LISTENERS ---

    def _format_title(self, author: str, title: str) -> str:
        artist = author
        separators = [' - ', ' – ', ': ']
        for sep in separators:
            if sep in title:
                parts = title.split(sep, 1)
                if len(parts[0]) < len(parts[1]) and len(parts[0]) > 0:
                    artist = parts[0]
                    title = parts[1]
                    break
        title = re.sub(r'\[.*?\]|\(.*?\)', '', title).strip(' -–:').strip()
        artist = artist.strip(' -–:').strip()
        return f"{artist} - {title}"

    async def _cleanup_player(self, guild: discord.Guild):
        vc_id = await self.config.guild(guild).audio_music_voice_channel_id()
        if not vc_id: return
        
        voice_channel = guild.get_channel(vc_id)
        if not voice_channel: return
        
        message_id = await self.config.guild(guild).audio_player_message_id()
        if not message_id: return

        try:
            message = await voice_channel.fetch_message(message_id)
            await message.delete()
        except (discord.NotFound, discord.Forbidden): pass
        await self.config.guild(guild).audio_player_message_id.clear()

    async def update_settings_message(self, guild: discord.Guild, message: Optional[discord.Message] = None):
        if not message:
            return

        settings = await self.config.guild(guild).all()
        is_enabled = settings.get('audio_is_enabled', False)
        vc_id = settings.get('audio_music_voice_channel_id')
        playlists = settings.get('audio_playlists', {})
        
        status_display = "🟢 Active" if is_enabled else "🔴 Inactive"
        vc_display = f"**{guild.get_channel(vc_id).name}** (`{vc_id}`)" if vc_id and guild.get_channel(vc_id) else "*Not configured*"
        playlist_display = "\n".join(f"• {name}" for name in playlists.keys()) or "*None*"

        embed = message.embeds[0]
        embed.description = "Use this panel to set the music channel and manage playlists."
        embed.clear_fields()
        embed.add_field(name="System Status", value=status_display, inline=False)
        embed.add_field(name="Music Channel", value=vc_display, inline=False)
        embed.add_field(name="Saved Playlists", value=playlist_display, inline=False)
        
        toggle_button = discord.utils.get(self.settings_view.children, custom_id="toggle_automation")
        if toggle_button:
            if is_enabled:
                toggle_button.label = "Disable"
                toggle_button.style = discord.ButtonStyle.danger
            else:
                toggle_button.label = "Enable"
                toggle_button.style = discord.ButtonStyle.success
        
        await message.edit(embed=embed, view=self.settings_view)


    async def get_cached_playlists(self):
        import time
        import aiohttp
        if not hasattr(self, "_playlist_cache"):
            self._playlist_cache = []
            self._playlist_cache_time = 0
            
        if time.time() - self._playlist_cache_time > 60:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://afterworkplay.com/api/db/playlists") as resp:
                        if resp.status == 200:
                            self._playlist_cache = await resp.json()
                            self._playlist_cache_time = time.time()
            except: pass
        return self._playlist_cache

    async def _debounced_update(self, guild: discord.Guild):
        await asyncio.sleep(1.5)
        await self._update_player_message(guild)

    def schedule_player_update(self, guild: discord.Guild):
        task = self.update_tasks.get(guild.id)
        if task:
            task.cancel()
        self.update_tasks[guild.id] = self.bot.loop.create_task(self._debounced_update(guild))

    async def _update_player_message(self, guild: discord.Guild):
        vc_id = await self.config.guild(guild).audio_music_voice_channel_id()
        if not vc_id: return
        
        channel = guild.get_channel(vc_id)
        if not channel: return
            
        player = None
        try:
            player = lavalink.get_player(guild.id)
        except lavalink.errors.PlayerNotFound:
            pass
            
        try:
            status_text = None
            if player and player.current:
                status_text = self._format_title(player.current.author, player.current.title)
                status_text = status_text[:100]
            await channel.edit(status=status_text, reason="Update music status")
        except discord.Forbidden:
            log.warning(f"Missing 'Manage Channel' permission in '{guild.name}' to update VC status.")
        except Exception as e:
            log.error(f"Error updating VC status: {e}")

        player_message_id = await self.config.guild(guild).audio_player_message_id()
        if not player_message_id: return
        
        try:
            message = await channel.fetch_message(player_message_id)
            is_playing = player and player.is_playing and not player.paused
            
            embed = discord.Embed(title="Music Player", color=discord.Color.green())
            embed.description = "Use the buttons below to control music."
            
            if player and player.current:
                formatted_title = self._format_title(player.current.author, player.current.title)
                embed.add_field(name="Now Playing", value=formatted_title, inline=False)
            else:
                embed.description = "Nothing is playing. Use the 'Song' button to request a track."
            
            if player and player.queue:
                tracks_to_show = player.queue[:1]
                if tracks_to_show:
                    next_track_title = self._format_title(tracks_to_show[0].author, tracks_to_show[0].title)
                    remaining_count = len(player.queue) - 1 
                    next_song_value = next_track_title
                    if remaining_count > 0:
                        next_song_value += f"\n\n... and {remaining_count} more."
                    embed.add_field(name="Next Song", value=next_song_value, inline=False)

            playlists = await self.get_cached_playlists()
            new_view = AudioPlayerView(self, is_playing=is_playing, playlists=playlists)
            await message.edit(embed=embed, view=new_view)
        except (discord.NotFound, discord.Forbidden):
            await self.config.guild(guild).audio_player_message_id.clear()

    async def _invoke_audio_command(self, interaction: discord.Interaction, command_name: str, **kwargs):
        audio_cog = self.bot.get_cog("Audio")
        if not audio_cog:
            await _send_owner_dm(self.bot, f"Failed to invoke `{command_name}`: Red Audio cog is not loaded.")
            return await interaction.response.defer()

        ctx = await self.bot.get_context(interaction.message)
        ctx.author = interaction.user
        ctx.command = self.bot.get_command(command_name)
        
        if command_name == "play":
            query = kwargs.get("query")
            vc_id = await self.config.guild(interaction.guild).audio_music_voice_channel_id()
            voice_channel = interaction.guild.get_channel(vc_id)
            if voice_channel:
                ctx.message.content = f"{ctx.prefix}play {query}"
                try:
                    await ctx.invoke(ctx.command, query=query)
                    await interaction.response.defer()
                except Exception as e:
                    log.error(f"Play command failed: {e}")
                    await interaction.response.defer()
        else:
            try:
                await ctx.invoke(ctx.command)
                await interaction.response.defer()
            except Exception as e:
                log.error(f"Command {command_name} failed: {e}")
                await interaction.response.defer()

    @commands.Cog.listener("on_red_audio_track_start")
    async def on_track_start(self, guild, track, requester):
        await self.bot.change_presence(activity=discord.Game(name="Music"))
        self.schedule_player_update(guild)

    @commands.Cog.listener("on_red_audio_track_pause")
    async def on_track_pause(self, guild, track, requester):
        self.schedule_player_update(guild)
        
    @commands.Cog.listener("on_red_audio_track_resume")
    async def on_track_resume(self, guild, track, requester):
        self.schedule_player_update(guild)

    @commands.Cog.listener("on_red_audio_player_stop")
    async def on_player_stop(self, guild, track, requester):
        await self.bot.change_presence(activity=None)
        self.schedule_player_update(guild)
        
    @commands.Cog.listener("on_red_audio_queue_end")
    async def on_queue_end(self, guild, track, requester):
        await self.bot.change_presence(activity=None)
        self.schedule_player_update(guild)

    @commands.Cog.listener("on_red_audio_track_add")
    async def on_track_add(self, guild, track, requester):
        self.schedule_player_update(guild)

    async def _process_voice_state_update_audio(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        if not await self.config.guild(guild).audio_is_enabled(): return
        
        voice_channel_id = await self.config.guild(guild).audio_music_voice_channel_id()
        if not voice_channel_id: return

        if after.channel and after.channel.id == voice_channel_id and len([m for m in after.channel.members if not m.bot]) == 1:
            voice_channel = after.channel
            await self._cleanup_player(guild)
            embed = discord.Embed(title="Music Player", description="Use the 'Song' button to request a track.", color=discord.Color.green())
            try:
                initial_view = AudioPlayerView(self, is_playing=False)
                player_message = await voice_channel.send(embed=embed, view=initial_view)
                await self.config.guild(guild).audio_player_message_id.set(player_message.id)
            except discord.Forbidden: log.error(f"Missing permissions to send messages in {voice_channel.name}")

        if before.channel and before.channel.id == voice_channel_id and not any(not m.bot for m in before.channel.members):
            await self._cleanup_player(guild)

    async def _process_audio_message(self, message: discord.Message):
        vc_id = await self.config.guild(message.guild).audio_music_voice_channel_id()
        if not vc_id or message.channel.id != vc_id: return

        if message.author.id == self.bot.user.id and message.embeds:
            if message.embeds[0].title == "Music Player":
                return

        player_message_id = await self.config.guild(message.guild).audio_player_message_id()
        if message.id != player_message_id:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound): pass

    # --- VOICE TEMP ROOMS METHODS ---

    async def _process_voice_state_update_rooms(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        config = await self.config.guild(guild).all()

        if not config.get("voice_enabled"): return
        source_id = config.get("voice_source_id")

        if after.channel and after.channel.id == source_id:
            try:
                def check(m, b, a):
                    return (
                        m.id == member.id
                        and b.channel and b.channel.id == source_id
                        and a.channel is not None
                        and a.channel.id != source_id
                    )

                _, _, moved_to_state = await self.bot.wait_for(
                    "voice_state_update", check=check, timeout=15.0
                )
                new_voice_channel = moved_to_state.channel

                async with self.config.guild(guild).voice_room_channels() as room_channels:
                    room_channels[str(new_voice_channel.id)] = {"owner_id": member.id}

                embed = discord.Embed(
                    title="Voice Channel Controls",
                    description=f"You are the owner of **{new_voice_channel.name}**.",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Current Owner", value=member.mention, inline=False)
                embed.add_field(name="Controls", value="Use buttons to manage members and privacy.", inline=False)
                embed.set_footer(text="e.Network | Available Right Now on Jellyfin")

                view = await VoiceChannelButtons.create(self, new_voice_channel)
                await new_voice_channel.send(content=member.mention, embed=embed, view=view)

            except asyncio.TimeoutError:
                message = (
                    f"User **{member.display_name}** joined the Source VC but was not moved within 15 seconds. "
                    "This usually means the external AutoRoom cog failed to create the channel."
                )
                log.warning(message)
                await _send_owner_dm(self.bot, f"Guild: {guild.name} (ID: {guild.id})\n{message}")

    # --- TV EMBED WEBHOOK REFORMATTER METHODS ---

    async def _process_tv_message(self, message: discord.Message):
        if not message.embeds: return
        data = await self.config.guild(message.guild).all()
        
        radarr_id = data.get('tv_radarr_webhook_id')
        sonarr_id = data.get('tv_sonarr_webhook_id')
        
        if not data.get('tv_enabled') or message.author.id not in [radarr_id, sonarr_id]:
            return

        for emb in message.embeds:
            new_embed = None
            match = re.match(r"^(.*?) - (?:S)?(\d+)[xE](\d+) - (.*)$", emb.title or "")

            if match:
                series_name = match.group(1).strip()
                season_num = int(match.group(2))
                episode_num = int(match.group(3))
                episode_title = match.group(4).strip()

                new_embed = discord.Embed(
                    title=series_name,
                    description=f"Season {season_num} Episode {episode_num:02d}",
                    color=emb.color
                )
                if emb.thumbnail:
                    new_embed.set_thumbnail(url=emb.thumbnail.url)
                
                overview_value = None
                if emb.fields:
                    for field in emb.fields:
                        if field.name.lower() == 'overview':
                            overview_value = field.value
                            break
                
                if overview_value:
                    new_embed.add_field(name=episode_title, value=overview_value, inline=False)
            else:
                new_embed = discord.Embed(
                    title=emb.title,
                    color=emb.color
                )
                if emb.thumbnail:
                    new_embed.set_thumbnail(url=emb.thumbnail.url)

                overview_value = None
                if emb.fields:
                    for field in emb.fields:
                        if field.name.lower() == 'overview':
                            overview_value = field.value
                            break
                new_embed.description = overview_value or emb.description

            if new_embed:
                new_embed.set_footer(text="e.Network | Available Right Now on Jellyfin")
                dest_channel = self.bot.get_channel(data.get('tv_dest_channel'))
                if dest_channel:
                    try:
                        await dest_channel.send(embed=new_embed)
                    except discord.Forbidden: 
                        await _send_owner_dm(self.bot, f"Failed to post embed in {dest_channel.mention} due to permissions.")

    # --- RSS READER METHODS ---

    async def _add_feed_to_config(self, guild: discord.Guild, feed_name: str, channel_id: int, url: str) -> Union[dict, str]:
        feeds_list = await self.config.guild(guild).rss_feeds()
        if any(f['name'] == feed_name for f in feeds_list):
            return "A feed with that name already exists."
        
        try:
            feedparser_obj = await self._fetch_feedparser_object(url)
        except Exception as e:
            log.error(f"Failed to fetch initial feed {url}: {e}", exc_info=True)
            return "Failed to fetch or parse the RSS feed URL. Check if it is a valid RSS/Atom link."

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
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(headers=self._headers, timeout=timeout) as session:
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    html = await resp.read()
            
            feedparser_obj = feedparser.parse(html)
            if feedparser_obj.bozo:
                raise ValueError(f"Bozo feed: {feedparser_obj.bozo_exception}")
                
            return feedparser_obj
        except Exception as e:
            raise Exception(f"Feed fetch failed: {e}")

    def _time_tag_validation(self, entry: SimpleNamespace) -> Optional[int]:
        entry_time = entry.get("updated_parsed", entry.get("published_parsed"))
        if isinstance(entry_time, time.struct_time):
            return int(time.mktime(entry_time))
        return None
        
    async def _update_last_scraped(self, feed_name: str, guild_id: int, title: str, link: str, entry_time: int):
        async with self.config.guild(guild_id).rss_feeds() as feeds:
             for feed in feeds:
                if feed['name'] == feed_name:
                    feed['last_title'] = title
                    feed['last_link'] = link
                    feed['last_time'] = entry_time
                    break
        
    async def read_feeds(self):
        await self.bot.wait_until_red_ready()
        while True:
            await asyncio.sleep(300)
            
            for guild_id, guild_data in (await self.config.all_guilds()).items():
                if not guild_data.get('rss_enabled'): continue
                
                guild = self.bot.get_guild(guild_id)
                if not guild or guild.unavailable: continue
                
                feeds_to_check = guild_data.get('rss_feeds', [])
                for feed in feeds_to_check:
                    try:
                        await self.check_and_post_feed(guild, feed)
                    except Exception as e:
                         log.error(f"Error processing feed {feed['name']} in {guild.name}: {e}", exc_info=True)
                         
    async def check_and_post_feed(self, guild: discord.Guild, feed: dict):
        channel = self.bot.get_channel(feed['channel_id'])
        if not channel or not channel.permissions_for(guild.me).send_messages: 
            return

        feedparser_obj = await self._fetch_feedparser_object(feed['url'])
        if not feedparser_obj.entries: return
        
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
            soup = BeautifulSoup(summary_html, 'html.parser')
            
            image_url = None
            first_image = soup.find("img")
            if first_image and first_image.has_attr('src'):
                image_url = first_image['src']

            summary_text = soup.get_text()
            
            if len(summary_text) > DESCRIPTION_LIMIT:
                suffix = f"\n\n[... Read Full Post Here]({current_link})"
                truncate_at = DESCRIPTION_LIMIT - len(suffix)
                summary_text = summary_text[:truncate_at] + suffix
            
            if feed['is_embed']:
                embed = discord.Embed(title=current_title, description=summary_text, url=current_link, color=discord.Color.blue())
                if current_time: embed.timestamp = datetime.fromtimestamp(current_time)
                if image_url:
                    embed.set_image(url=image_url)

                try: await channel.send(embed=embed)
                except discord.Forbidden: return
            else:
                message = f"**{current_title}**\n{summary_text}\n{current_link}"
                try: await channel.send(message)
                except discord.Forbidden: return

        if newest_post_time > 0 and newest_post_time > feed['last_time']:
            await self._update_last_scraped(feed['name'], guild.id, newest_post_title, newest_post_link, newest_post_time)

    # --- HIDE VISIBILITY METHODS ---

    async def _is_managed_category_hidden(self, guild: discord.Guild) -> bool:
        settings = await self.config.guild(guild).all()
        category_id = settings.get('hide_managed_category_id')
        category = guild.get_channel(category_id)
        
        if not category or not isinstance(category, discord.CategoryChannel):
            return False 

        admin_roles = await self._get_admin_roles(guild)
        for role in admin_roles:
            if role not in guild.me.roles and role != guild.default_role:
                overwrite = category.overwrites_for(role)
                if overwrite.view_channel is False:
                    return True
        return False

    async def _get_admin_roles(self, guild: discord.Guild):
        admin_roles = []
        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_channels:
                admin_roles.append(role)
        return admin_roles

    async def _apply_perms_to_category(self, guild: discord.Guild, perm_action: callable):
        settings = await self.config.guild(guild).all()
        category_id = settings.get('hide_managed_category_id')
        
        if not category_id:
            await _send_owner_dm(self.bot, f"Permission update failed in **{guild.name}**. Category ID is not configured.")
            return

        category = guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            await _send_owner_dm(self.bot, f"Permission update failed in **{guild.name}**. Configured ID `{category_id}` is not a category.")
            return

        admin_roles = await self._get_admin_roles(guild)

        # Apply permissions directly to the Category Channel
        for role in admin_roles:
            if role not in guild.me.roles and role != guild.default_role:
                try:
                    await perm_action(category, role, reason="Managed by AfterworkHide")
                except discord.Forbidden:
                    log.warning(f"Could not modify admin perms for category '{category.name}' and role '{role.name}'.")

        # Apply permissions to all text and voice channels within the category
        channels_to_manage = [
            c for c in category.channels if isinstance(c, (discord.TextChannel, discord.VoiceChannel))
        ]
        for channel in channels_to_manage:
            for role in admin_roles:
                if role not in guild.me.roles and role != guild.default_role:
                    try:
                        await perm_action(channel, role, reason="Managed by AfterworkHide")
                    except discord.Forbidden:
                        log.warning(f"Could not modify admin perms for channel '{channel.name}' and role '{role.name}'.")

    # --- UNIFIED EVENT LISTENERS ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild: return
        
        # 1. Process TV Sonarr/Radarr webhooks
        await self._process_tv_message(message)
        
        # 2. Process Audio channel cleanup
        await self._process_audio_message(message)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot: return
        
        # 1. Voice room creation/ownership handling
        await self._process_voice_state_update_rooms(member, before, after)
        
        # 2. Audio player spawning/cleanup handling
        await self._process_voice_state_update_audio(member, before, after)


# --- MEMBER MODALS AND VIEWS ---


# --- REPOST AUTO-POSTER ---

class RepostAddLinkModal(discord.ui.Modal, title="Add Module Repost Link"):
    module_input = discord.ui.TextInput(label="Module ID (e.g. ark, dune, global)", style=discord.TextStyle.short, required=True, max_length=25)
    channel_input = discord.ui.TextInput(label="Channel ID", style=discord.TextStyle.short, required=True, max_length=25)

    def __init__(self, cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        module_id = self.module_input.value.strip().lower()
        if module_id == 'global':
            module_id = 'global' # We will use 'global' key for null modules
            
        try:
            channel_id = int(self.channel_input.value.strip())
        except ValueError:
            return await interaction.followup.send("❌ **Error:** Channel ID must be a number.", ephemeral=True)
            
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("❌ **Error:** Text Channel not found.", ephemeral=True)
            
        async with self.cog.config.guild(interaction.guild).repost_channels() as channels:
            channels[module_id] = channel_id
                
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"Added Repost Link for {module_id}"))
        await _update_repost_setup_embed(self.cog, interaction.guild, embed)
        await self.original_message.edit(embed=embed, view=RepostSetupView(self.cog))
        await interaction.followup.send(f"✅ News & Events for `{module_id}` will now be posted to {channel.mention}.", ephemeral=True)

class RepostSetupView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await self.cog.bot.is_owner(interaction.user):
            return True
        await _send_owner_dm(self.cog.bot, f"User {interaction.user.display_name} attempted to use owner controls in {interaction.guild.name}.")
        return False

    @discord.ui.button(label="Target Channel", style=discord.ButtonStyle.primary, custom_id="repost_add_link")
    async def add_link_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RepostAddLinkModal(self.cog, interaction.message))
        
    @discord.ui.button(label="Enable / Disable", style=discord.ButtonStyle.secondary, custom_id="repost_toggle_enable")
    async def toggle_enable_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.cog.config.guild(interaction.guild).repost_enabled()
        await self.cog.config.guild(interaction.guild).repost_enabled.set(not current)
        
        embed = interaction.message.embeds[0]
        status = "Enabled" if not current else "Disabled"
        embed.set_footer(text=_get_admin_footer(interaction, f"{status} Reposter"))
        await _update_repost_setup_embed(self.cog, interaction.guild, embed)
        await interaction.response.edit_message(embed=embed, view=self)

async def _update_repost_setup_embed(cog, guild: discord.Guild, embed: discord.Embed):
    channels = await cog.config.guild(guild).repost_channels()
    enabled = await cog.config.guild(guild).repost_enabled()
    
    embed.title = "Website News & Events Reposter Setup"
    embed.description = "Link website Modules to Discord Channels. When a new post is made on the website for a linked module, it will automatically be posted here."
    embed.color = discord.Color.gold()
    embed.clear_fields()
    
    status_emoji = "🟢" if enabled else "🔴"
    status_text = "Enabled" if enabled else "Disabled"
    embed.add_field(name="Status", value=f"{status_emoji} **{status_text}**", inline=False)
    
    if not channels:
        embed.add_field(name="Linked Modules", value="None configured. Click 'Target Channel' below.", inline=False)
    else:
        text = ""
        for mod, chan_id in channels.items():
            text += f"**{mod.upper()}** ➔ <#{chan_id}>\n"
        embed.add_field(name="Linked Modules", value=text, inline=False)

# Add this method inside Afterwork class dynamically:
async def repost_polling_task(self):
    await self.bot.wait_until_ready()
    while not self.bot.is_closed():
        try:
            async with aiohttp.ClientSession() as session:
                # 1. Check News
                async with session.get("https://afterworkplay.com/api/db/news") as resp:
                    if resp.status == 200:
                        news_data = await resp.json()
                        for guild in self.bot.guilds:
                            last_news_id = await self.config.guild(guild).repost_last_news_id()
                            channels = await self.config.guild(guild).discord_channels()
                            if not channels: continue
                            
                            highest_seen_news = last_news_id
                            
                            # Sort old to new for posting
                            new_posts = [n for n in news_data if int(n["id"]) > last_news_id]
                            new_posts.sort(key=lambda x: int(x["id"]))
                            
                            for n in new_posts:
                                nid = int(n["id"])
                                if nid > highest_seen_news: highest_seen_news = nid
                                
                                mod_id = n.get("module_id") or "global"
                                mod_id = mod_id.lower()
                                
                                enabled = await self.config.guild(guild).discord_enabled()
                                if enabled and mod_id in channels:
                                    chan_id = channels[mod_id]
                                    channel = guild.get_channel(chan_id)
                                    if channel:
                                        embed = discord.Embed(
                                            title=n.get("title", "New News!"),
                                            description=n.get("content", ""),
                                            color=discord.Color.blue(),
                                            url="https://afterworkplay.com"
                                        )
                                        if n.get("subtitle"):
                                            embed.add_field(name="Details", value=n.get("subtitle"), inline=False)
                                        if n.get("image_url"):
                                            embed.set_image(url=n.get("image_url"))
                                        embed.set_footer(text=f"📰 News • Module: {mod_id.upper()}")
                                        try:
                                            await channel.send(embed=embed)
                                        except discord.Forbidden:
                                            pass
                            if highest_seen_news > last_news_id:
                                await self.config.guild(guild).repost_last_news_id.set(highest_seen_news)

                # 2. Check Events
                async with session.get("https://afterworkplay.com/api/db/events") as resp:
                    if resp.status == 200:
                        events_data = await resp.json()
                        for guild in self.bot.guilds:
                            last_events_id = await self.config.guild(guild).repost_last_events_id()
                            channels = await self.config.guild(guild).discord_channels()
                            if not channels: continue
                            
                            highest_seen_event = last_events_id
                            
                            new_events = [e for e in events_data if int(e["id"]) > last_events_id]
                            new_events.sort(key=lambda x: int(x["id"]))
                            
                            for e in new_events:
                                eid = int(e["id"])
                                if eid > highest_seen_event: highest_seen_event = eid
                                
                                mod_id = e.get("module_id") or "global"
                                mod_id = mod_id.lower()
                                
                                enabled = await self.config.guild(guild).discord_enabled()
                                if enabled and mod_id in channels:
                                    chan_id = channels[mod_id]
                                    channel = guild.get_channel(chan_id)
                                    if channel:
                                        embed = discord.Embed(
                                            title=e.get("title", "New Event!"),
                                            description=e.get("content", ""),
                                            color=discord.Color.green(),
                                            url="https://afterworkplay.com"
                                        )
                                        if e.get("subtitle"):
                                            embed.add_field(name="Details", value=e.get("subtitle"), inline=False)
                                            
                                        # Parse Event Times
                                        if e.get("start_date") and e.get("end_date"):
                                            embed.add_field(name="Event Active From", value=f"{e['start_date']} to {e['end_date']}", inline=False)
                                            
                                        if e.get("image_url"):
                                            embed.set_image(url=e.get("image_url"))
                                        embed.set_footer(text=f"🗓️ Event • Module: {mod_id.upper()}")
                                        try:
                                            await channel.send(embed=embed)
                                        except discord.Forbidden:
                                            pass
                            if highest_seen_event > last_events_id:
                                await self.config.guild(guild).repost_last_events_id.set(highest_seen_event)

        except Exception as e:
            import logging
            logging.getLogger("red.Afterwork").error(f"Repost Polling Task Error: {e}")
            
        await __import__('asyncio').sleep(60)

Afterwork.repost_polling_task = repost_polling_task


class DiscordChannelModal(discord.ui.Modal, title="Add Discord Embed Channel"):
    module_id = discord.ui.TextInput(
        label="Module ID (ark, dune, global)",
        placeholder="e.g. ark",
        required=True,
        max_length=50
    )
    channel_id = discord.ui.TextInput(
        label="Target Channel ID",
        placeholder="e.g. 123456789012345678",
        required=True,
        max_length=25
    )

    def __init__(self, cog, **kwargs):
        super().__init__(**kwargs)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        mod_id = self.module_id.value.strip().lower()
        chan_id_str = self.channel_id.value.strip()
        
        try:
            chan_id = int(chan_id_str)
        except ValueError:
            return await interaction.response.send_message("❌ Invalid Channel ID. Must be a number.", ephemeral=True)

        chan = interaction.guild.get_channel(chan_id)
        if not chan:
            return await interaction.response.send_message("❌ Channel not found in this server.", ephemeral=True)

        async with self.cog.config.guild(interaction.guild).discord_channels() as channels:
            channels[mod_id] = chan_id
            
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed(title="Manage Discord Setup")
        await _update_discord_setup_embed(self.cog, interaction.guild, embed)
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(f"✅ Set {mod_id} to post to <#{chan_id}>.", ephemeral=True)

class DiscordRemoveSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Select a module channel to remove...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        mod_id = self.values[0]
        async with self.view.cog.config.guild(interaction.guild).discord_channels() as channels:
            if mod_id in channels:
                del channels[mod_id]
                
        embed = interaction.message.embeds[0]
        await _update_discord_setup_embed(self.view.cog, interaction.guild, embed)
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(f"✅ Removed {mod_id} target.", ephemeral=True)

class DiscordRemoveView(discord.ui.View):
    def __init__(self, cog, interaction):
        super().__init__(timeout=60)
        self.cog = cog
        self.original_interaction = interaction

    async def on_timeout(self):
        try:
            await self.original_interaction.edit_original_response(view=None)
        except: pass

class DiscordSetupView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Set Channel", style=discord.ButtonStyle.primary, custom_id="discord_add_link")
    async def add_link_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DiscordChannelModal(self.cog))

    @discord.ui.button(label="Remove Channel", style=discord.ButtonStyle.secondary, custom_id="discord_remove_link")
    async def remove_link_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        channels = await self.cog.config.guild(interaction.guild).discord_channels()
        if not channels:
            return await interaction.response.send_message("❌ No targets set up yet.", ephemeral=True)
            
        options = [
            discord.SelectOption(label=f"Module: {m}", description=f"Channel: {c}", value=m)
            for m, c in channels.items()
        ]
        
        view = DiscordRemoveView(self.cog, interaction)
        select = DiscordRemoveSelect(options)
        view.add_item(select)
        
        await interaction.response.send_message("Select a target to remove:", view=view, ephemeral=True)

    @discord.ui.button(label="Toggle Status", style=discord.ButtonStyle.success, custom_id="discord_toggle_enable")
    async def toggle_enable_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.cog.config.guild(interaction.guild).discord_enabled()
        new_state = not current
        await self.cog.config.guild(interaction.guild).discord_enabled.set(new_state)
        
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed(title="Manage Discord Setup")
        await _update_discord_setup_embed(self.cog, interaction.guild, embed)
        view = DiscordSetupView(self.cog, initial_enabled=new_state)
        await interaction.response.edit_message(embed=embed, view=view)


async def _update_discord_setup_embed(cog, guild: discord.Guild, embed: discord.Embed):
    channels = await cog.config.guild(guild).discord_channels()
    enabled = await cog.config.guild(guild).discord_enabled()
    
    embed.description = "Manage dynamic custom embeds sent from the Web Dashboard."
    embed.clear_fields()
    
    status_str = "✅ **Enabled**" if enabled else "❌ **Disabled**"
    embed.add_field(name="Status", value=status_str, inline=False)
    
    if channels:
        ch_list = [f"**{m}** -> <#{c}>" for m, c in channels.items()]
        embed.add_field(name="Target Channels", value="\n".join(ch_list), inline=False)
    else:
        embed.add_field(name="Target Channels", value="None configured. Use 'Set Channel'.", inline=False)
    return embed


async def discord_polling_task(self):
    await self.bot.wait_until_ready()
    import aiohttp
    import json
    import logging
    import discord
    log = logging.getLogger("red.afterwork")
    while not self.bot.is_closed():
        try:
            async with aiohttp.ClientSession() as session:
                # 1. Fetch Embeds from API
                async with session.get("https://afterworkplay.com/api/db/embeds") as resp:
                    if resp.status == 200:
                        embeds_data = await resp.json()
                        for guild in self.bot.guilds:
                            channels = await self.config.guild(guild).discord_channels()
                            if not channels: continue
                            enabled = await self.config.guild(guild).discord_enabled()
                            if not enabled: continue
                            
                            seen_ids = await self.config.guild(guild).discord_last_embeds_ids()
                            if type(seen_ids) is not dict: seen_ids = {}
                            
                            for emb in embeds_data:
                                eid = str(emb["id"])
                                mod_id = (emb.get("module_id") or "global").lower()
                                
                                if mod_id not in channels: continue
                                channel_id = channels[mod_id]
                                channel = guild.get_channel(int(channel_id))
                                if not channel: continue
                                
                                embed_json = emb.get("embed_json") or "{}"
                                try: e_dict = json.loads(embed_json)
                                except: e_dict = {}
                                discord_embed = discord.Embed.from_dict(e_dict) if e_dict else discord.Embed(title=emb["title"])
                                
                                if emb.get("include_status"):
                                    try:
                                        async with session.get("https://afterworkplay.com/api/status") as st_resp:
                                            if st_resp.status == 200:
                                                st_data = await st_resp.json()
                                                servers_to_include = []
                                                try:
                                                    if emb.get("status_servers"): servers_to_include = json.loads(emb.get("status_servers"))
                                                except: pass
                                                raw_servers = st_data
                                                server_list = raw_servers if isinstance(raw_servers, list) else (raw_servers.get("instances") or raw_servers.get("Instances") or raw_servers.get("Result") or raw_servers.get("result") or [])
                                                flat_servers = []
                                                if isinstance(server_list, list):
                                                    if len(server_list) > 0 and isinstance(server_list[0], dict) and "AvailableInstances" in server_list[0]:
                                                        for t in server_list:
                                                            if t.get("AvailableInstances"): flat_servers.extend(t["AvailableInstances"])
                                                    else: flat_servers = server_list
                                                for s_data in flat_servers:
                                                    if not isinstance(s_data, dict): continue
                                                    s_name = s_data.get("InstanceName", "Unknown")
                                                    if not servers_to_include or s_name in servers_to_include:
                                                        state = s_data.get("State", 0)
                                                        status_emoji = "🟢" if state == 20 else "🔴"
                                                        metrics = s_data.get("Metrics", {})
                                                        players = metrics.get("ActiveUsers", 0)
                                                        max_players = metrics.get("MaxUsers", 0)
                                                        discord_embed.add_field(name=f"{status_emoji} {s_name}", value=f"Players: {players}/{max_players}", inline=True)
                                    except Exception as e:
                                        log.error(f"Error fetching status for embed: {e}")

                                msg = None
                                msg_id = seen_ids.get(eid)
                                if msg_id:
                                    try:
                                        msg = await channel.fetch_message(int(msg_id))
                                        await msg.edit(embed=discord_embed)
                                    except: msg = None
                                        
                                if not msg:
                                    msg = await channel.send(embed=discord_embed)
                                    seen_ids[eid] = str(msg.id)
                                    await self.config.guild(guild).discord_last_embeds_ids.set(seen_ids)
                                    if emb.get("pin_message"):
                                        try: await msg.pin()
                                        except: pass

                # 2. Fetch News from API
                async with session.get("https://afterworkplay.com/api/db/news") as resp:
                    if resp.status == 200:
                        news_data = await resp.json()
                        for guild in self.bot.guilds:
                            channels = await self.config.guild(guild).discord_channels()
                            if not channels: continue
                            enabled = await self.config.guild(guild).discord_enabled()
                            if not enabled: continue
                            
                            seen_ids = await self.config.guild(guild).discord_last_news_ids()
                            if type(seen_ids) is not dict: seen_ids = {}
                            
                            for n in news_data:
                                eid = str(n["id"])
                                mod_id = (n.get("module_id") or "global").lower()
                                
                                if mod_id not in channels: continue
                                channel_id = channels[mod_id]
                                channel = guild.get_channel(int(channel_id))
                                if not channel: continue
                                
                                title = n.get("title") or "News"
                                subtitle = n.get("subtitle") or ""
                                content = n.get("content") or ""
                                image_url = n.get("image_url")
                                
                                discord_embed = discord.Embed(title=title, description=content, color=discord.Color.red())
                                if subtitle: discord_embed.set_author(name=subtitle)
                                if image_url:
                                    full_url = f"https://afterworkplay.com{image_url}" if image_url.startswith("/") else image_url
                                    discord_embed.set_image(url=full_url)
                                
                                msg = None
                                msg_id = seen_ids.get(eid)
                                if msg_id:
                                    try:
                                        msg = await channel.fetch_message(int(msg_id))
                                        await msg.edit(embed=discord_embed)
                                    except: msg = None
                                        
                                if not msg:
                                    msg = await channel.send(embed=discord_embed)
                                    seen_ids[eid] = str(msg.id)
                                    await self.config.guild(guild).discord_last_news_ids.set(seen_ids)

                # 3. Fetch Events from API
                async with session.get("https://afterworkplay.com/api/db/events") as resp:
                    if resp.status == 200:
                        events_data = await resp.json()
                        for guild in self.bot.guilds:
                            channels = await self.config.guild(guild).discord_channels()
                            if not channels: continue
                            enabled = await self.config.guild(guild).discord_enabled()
                            if not enabled: continue
                            
                            seen_ids = await self.config.guild(guild).discord_last_events_ids()
                            if type(seen_ids) is not dict: seen_ids = {}
                            
                            for ev in events_data:
                                eid = str(ev["id"])
                                mod_id = (ev.get("module_id") or "global").lower()
                                
                                if mod_id not in channels: continue
                                channel_id = channels[mod_id]
                                channel = guild.get_channel(int(channel_id))
                                if not channel: continue
                                
                                title = ev.get("title") or "Event"
                                desc = ev.get("description") or ""
                                start_date = ev.get("start_date") or ""
                                start_time = ev.get("start_time") or ""
                                start_str = f"{start_date} {start_time}".strip()
                                
                                discord_embed = discord.Embed(title=f"📅 {title}", description=desc, color=discord.Color.orange())
                                if start_str: discord_embed.add_field(name="Date/Time", value=start_str)
                                
                                msg = None
                                msg_id = seen_ids.get(eid)
                                if msg_id:
                                    try:
                                        msg = await channel.fetch_message(int(msg_id))
                                        await msg.edit(embed=discord_embed)
                                    except: msg = None
                                        
                                if not msg:
                                    msg = await channel.send(embed=discord_embed)
                                    seen_ids[eid] = str(msg.id)
                                    await self.config.guild(guild).discord_last_events_ids.set(seen_ids)

        except Exception as e:
            log.error(f"Error in discord polling task: {e}")
            
        import asyncio
        await asyncio.sleep(60)

Afterwork.discord_polling_task = discord_polling_task

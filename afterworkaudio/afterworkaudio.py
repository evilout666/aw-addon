import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime
from typing import Union, Optional, Dict

log = logging.getLogger("red.AfterworkAudio")


# --- MODALS ---

class SetChannelModal(discord.ui.Modal, title="Set Music Voice Channel"):
    channel_id_input = discord.ui.TextInput(
        label="Voice Channel ID",
        style=discord.TextStyle.short,
        placeholder="Paste the ID of the voice channel here.",
        required=True,
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        channel_id_str = self.channel_id_input.value.strip()
        try:
            channel_id = int(channel_id_str)
        except ValueError:
            return await interaction.response.send_message("❌ That is not a valid ID. Please provide a numerical ID.", ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            return await interaction.response.send_message("❌ A voice channel with that ID was not found.", ephemeral=True)

        await self.cog.config.guild(interaction.guild).music_voice_channel_id.set(channel.id)
        await interaction.response.send_message(f"✅ Music channel has been set to **{channel.name}**.", ephemeral=True)
        await self.cog.update_settings_message(interaction.guild, interaction.message)


class AddPlaylistModal(discord.ui.Modal, title="Add a Playlist"):
    playlist_name = discord.ui.TextInput(label="Playlist Name", placeholder="e.g., Lofi Beats", required=True)
    playlist_url = discord.ui.TextInput(label="Playlist URL", placeholder="Paste a YouTube or Spotify URL.", required=True)

    def __init__(self, config: Config):
        super().__init__()
        self.config = config

    async def on_submit(self, interaction: discord.Interaction):
        name = self.playlist_name.value.strip()
        url = self.playlist_url.value.strip()
        async with self.config.guild(interaction.guild).playlists() as playlists:
            playlists[name] = url
        await interaction.response.send_message(f"✅ Playlist '{name}' has been saved.", ephemeral=True)


class PlayerPlayModal(discord.ui.Modal, title="Play Music"):
    query_input = discord.ui.TextInput(label="URL or Saved Playlist Name", placeholder="Paste a URL or type a saved playlist name.", required=True)

    def __init__(self, cog: commands.Cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        query = self.query_input.value.strip()
        all_playlists = await self.cog.config.guild(interaction.guild).playlists()
        final_query = all_playlists.get(query, query)
        await self.cog._invoke_audio_command(interaction, "play", query=final_query)


# --- VIEWS ---

class PlayerView(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Play", style=discord.ButtonStyle.success, custom_id="player_play")
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerPlayModal(self.cog))

    @discord.ui.button(label="Play/Pause", style=discord.ButtonStyle.primary, custom_id="player_pause")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._invoke_audio_command(interaction, "pause")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, custom_id="player_skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._invoke_audio_command(interaction, "skip")

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, custom_id="player_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._invoke_audio_command(interaction, "stop")


class SettingsView(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Channel ID", style=discord.ButtonStyle.primary, custom_id="set_voice_channel")
    async def set_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetChannelModal(self.cog))
    
    @discord.ui.button(label="Add", style=discord.ButtonStyle.secondary, custom_id="add_playlist")
    async def add_playlist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddPlaylistModal(self.cog.config))

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.secondary, custom_id="remove_playlist")
    async def remove_playlist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        playlists = await self.cog.config.guild(interaction.guild).playlists()
        if not playlists:
            return await interaction.response.send_message("❌ No playlists saved.", ephemeral=True)

        options = [discord.SelectOption(label=name) for name in playlists.keys()]
        select_menu = discord.ui.Select(placeholder="Select a playlist to remove...", options=options)

        async def select_callback(select_interaction: discord.Interaction):
            playlist_name = select_interaction.data["values"][0]
            async with self.cog.config.guild(interaction.guild).playlists() as pls:
                if playlist_name in pls: del pls[playlist_name]
            await select_interaction.response.send_message(f"✅ Playlist '{playlist_name}' removed.", ephemeral=True, view=None)

        select_menu.callback = select_callback
        temp_view = discord.ui.View(timeout=180)
        temp_view.add_item(select_menu)
        await interaction.response.send_message("Please choose a playlist:", view=temp_view, ephemeral=True)

    @discord.ui.button(label="Enable/Disable", style=discord.ButtonStyle.grey, custom_id="toggle_automation")
    async def toggle_automation_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_state = await self.cog.config.guild(interaction.guild).is_enabled()
        new_state = not current_state
        await self.cog.config.guild(interaction.guild).is_enabled.set(new_state)
        
        await self.cog.update_settings_message(interaction.guild, interaction.message)
        await interaction.response.defer()


# --- MAIN COG CLASS ---

class AfterworkAudio(commands.Cog, name="AfterworkAudio"):
    """A dynamic, automated music player system."""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6677889901, force_registration=True)
        self.config.register_guild(
            music_voice_channel_id=None,
            music_text_channel_id=None,
            settings_message_id=None,
            player_message_id=None,
            is_enabled=False,
            playlists={},
        )
        self.settings_view = SettingsView(self)
        self.player_view = PlayerView(self)

    async def cog_load(self):
        self.bot.add_view(self.settings_view)
        self.bot.add_view(self.player_view)

    async def _cleanup_player(self, guild: discord.Guild):
        text_channel_id = await self.config.guild(guild).music_text_channel_id()
        message_id = await self.config.guild(guild).player_message_id()
        if not text_channel_id or not message_id: return
        channel = guild.get_channel(text_channel_id)
        if not channel: return

        try:
            message = await channel.fetch_message(message_id)
            await message.delete()
        except (discord.NotFound, discord.Forbidden): pass
        await self.config.guild(guild).player_message_id.clear()

    async def update_settings_message(self, guild: discord.Guild, message: Optional[discord.Message] = None):
        """Rebuilds and edits the main settings message to show current status."""
        if not message:
            settings_message_id = await self.config.guild(guild).settings_message_id()
            text_channel_id = await self.config.guild(guild).music_text_channel_id()
            if not settings_message_id or not text_channel_id: return
            channel = guild.get_channel(text_channel_id)
            if not channel: return
            try:
                message = await channel.fetch_message(settings_message_id)
            except (discord.NotFound, discord.Forbidden): return

        is_enabled = await self.config.guild(guild).is_enabled()
        vc_id = await self.config.guild(guild).music_voice_channel_id()
        
        status_display = "🟢 Active" if is_enabled else "🔴 Inactive"
        
        if vc_id and (channel := guild.get_channel(vc_id)):
            channel_display = f"**{channel.name}** (`{channel.id}`)"
        else:
            channel_display = "*Not configured*"

        embed = message.embeds[0]
        embed.clear_fields()
        embed.add_field(name="System Status", value=status_display, inline=False)
        embed.add_field(name="Channel", value=channel_display, inline=False)
        
        # Get the button from the cog's persistent view instance
        toggle_button = discord.utils.get(self.settings_view.children, custom_id="toggle_automation")
        if is_enabled:
            toggle_button.label = "Disable"
            toggle_button.style = discord.ButtonStyle.danger
        else:
            toggle_button.label = "Enable"
            toggle_button.style = discord.ButtonStyle.success
        
        # Pass the cog's persistent view instance to the edit method
        await message.edit(embed=embed, view=self.settings_view)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot: return
        guild = member.guild
        if not await self.config.guild(guild).is_enabled(): return
        voice_channel_id = await self.config.guild(guild).music_voice_channel_id()
        if not voice_channel_id: return

        if after.channel and after.channel.id == voice_channel_id and len(after.channel.members) == 1:
            await self._cleanup_player(guild)
            text_channel_id = await self.config.guild(guild).music_text_channel_id()
            text_channel = guild.get_channel(text_channel_id)
            if not text_channel: return
            embed = discord.Embed(title="Music Controls", description="Session started! Use buttons to control music.", color=discord.Color.green())
            try:
                player_message = await text_channel.send(embed=embed, view=self.player_view)
                await player_message.pin(reason="Active Music Session")
                await self.config.guild(guild).player_message_id.set(player_message.id)
            except discord.Forbidden: log.error(f"Missing permissions in {text_channel.name}")

        if before.channel and before.channel.id == voice_channel_id and not before.channel.members:
            await self._cleanup_player(guild)

    async def _invoke_audio_command(self, interaction: discord.Interaction, command_name: str, *, query: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not interaction.user.voice:
            return await interaction.followup.send("❌ You must be in a voice channel.", ephemeral=False)
        command = self.bot.get_command(command_name)
        if not command: return await interaction.followup.send(f"❌ Command not found.", ephemeral=False)
        try:
            ctx = await self.bot.get_context(interaction, cls=commands.Context)
            ctx.author = interaction.user
            await command.invoke(ctx, *([query] if query else []))
            await interaction.followup.send(f"✅ Executed `{command_name}`.", ephemeral=True)
        except Exception as e:
            log.error(f"Error invoking '{command_name}': {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred.", ephemeral=False)

    @commands.group(name="afterworkaudio")
    @commands.admin_or_permissions(manage_guild=True)
    async def afterworkaudio_group(self, ctx: commands.Context):
        """Manage the AfterworkAudio system."""
        if not ctx.invoked_subcommand: await ctx.send_help()

    @afterworkaudio_group.command(name="deploy")
    async def afterworkaudio_deploy(self, ctx: commands.Context):
        """Deploys the persistent settings panel."""
        await self.config.guild(ctx.guild).music_text_channel_id.set(ctx.channel.id)
        
        is_enabled = await self.config.guild(ctx.guild).is_enabled()
        vc_id = await self.config.guild(ctx.guild).music_voice_channel_id()
        
        status_display = "🟢 Active" if is_enabled else "🔴 Inactive"
        
        if vc_id and (channel := ctx.guild.get_channel(vc_id)):
            channel_display = f"**{channel.name}** (`{channel.id}`)"
        else:
            channel_display = "*Not configured*"
            
        embed = discord.Embed(
            title="Music Channel Control",
            description="Use this panel to set the music voice channel where the player will be active.",
            color=await ctx.embed_color()
        )
        embed.add_field(name="System Status", value=status_display, inline=False)
        embed.add_field(name="Channel", value=channel_display, inline=False)
        
        toggle_button = discord.utils.get(self.settings_view.children, custom_id="toggle_automation")
        if is_enabled:
            toggle_button.label = "Disable"
            toggle_button.style = discord.ButtonStyle.danger
        else:
            toggle_button.label = "Enable"
            toggle_button.style = discord.ButtonStyle.success

        msg = await ctx.send(embed=embed, view=self.settings_view)
        await self.config.guild(ctx.guild).settings_message_id.set(msg.id)

async def setup(bot):
    cog = AfterworkAudio(bot)
    await bot.add_cog(cog)

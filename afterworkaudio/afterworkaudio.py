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

    def __init__(self, config: Config):
        super().__init__()
        self.config = config

    async def on_submit(self, interaction: discord.Interaction):
        channel_id_str = self.channel_id_input.value.strip()
        try:
            channel_id = int(channel_id_str)
        except ValueError:
            return await interaction.response.send_message("❌ That is not a valid ID. Please provide a numerical ID.", ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message("❌ A channel with that ID could not be found on this server.", ephemeral=True)
        
        if not isinstance(channel, discord.VoiceChannel):
            return await interaction.response.send_message(f"❌ **{channel.name}** is not a voice channel.", ephemeral=True)

        await self.config.guild(interaction.guild).music_voice_channel_id.set(channel.id)
        await interaction.response.send_message(f"✅ Music channel has been set to **{channel.name}**.", ephemeral=True)


class AddPlaylistModal(discord.ui.Modal, title="Add a Playlist"):
    playlist_name = discord.ui.TextInput(
        label="Playlist Name",
        style=discord.TextStyle.short,
        placeholder="e.g., Lofi Beats, Workout Mix",
        required=True,
    )
    playlist_url = discord.ui.TextInput(
        label="Playlist URL",
        style=discord.TextStyle.short,
        placeholder="Paste a YouTube or Spotify playlist URL here.",
        required=True,
    )

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
    query_input = discord.ui.TextInput(
        label="URL or Saved Playlist Name",
        style=discord.TextStyle.short,
        placeholder="Paste a song/playlist URL or type a saved playlist name.",
        required=True,
    )

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

    @discord.ui.button(label="Play", style=discord.ButtonStyle.success, custom_id="player_play", emoji="🎵")
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerPlayModal(self.cog))

    @discord.ui.button(label="Play/Pause", style=discord.ButtonStyle.primary, custom_id="player_pause", emoji="⏯️")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._invoke_audio_command(interaction, "pause")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, custom_id="player_skip", emoji="⏭️")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._invoke_audio_command(interaction, "skip")

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, custom_id="player_stop", emoji="⏹️")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._invoke_audio_command(interaction, "stop")


class SettingsView(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="🔊 Set Music Channel", style=discord.ButtonStyle.primary, custom_id="set_voice_channel")
    async def set_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetChannelModal(self.cog.config))
    
    @discord.ui.button(label="➕ Add Playlist", style=discord.ButtonStyle.secondary, custom_id="add_playlist")
    async def add_playlist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddPlaylistModal(self.cog.config))

    @discord.ui.button(label="➖ Remove Playlist", style=discord.ButtonStyle.secondary, custom_id="remove_playlist")
    async def remove_playlist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        playlists = await self.cog.config.guild(interaction.guild).playlists()
        if not playlists:
            return await interaction.response.send_message("❌ No playlists have been saved yet.", ephemeral=True)

        options = [discord.SelectOption(label=name) for name in playlists.keys()]
        
        select_menu = discord.ui.Select(placeholder="Select a playlist to remove...", options=options)

        async def select_callback(select_interaction: discord.Interaction):
            playlist_name = select_interaction.data["values"][0]
            async with self.cog.config.guild(interaction.guild).playlists() as pls:
                if playlist_name in pls:
                    del pls[playlist_name]
            await select_interaction.response.send_message(f"✅ Playlist '{playlist_name}' has been removed.", ephemeral=True)
            self.clear_items()
            await interaction.edit_original_response(view=self)

        select_menu.callback = select_callback
        
        temp_view = discord.ui.View(timeout=180)
        temp_view.add_item(select_menu)
        await interaction.response.send_message("Please choose a playlist to remove:", view=temp_view, ephemeral=True)

    @discord.ui.button(label="Toggle Automation", style=discord.ButtonStyle.danger, custom_id="toggle_automation")
    async def toggle_automation_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_state = await self.cog.config.guild(interaction.guild).is_enabled()
        new_state = not current_state
        await self.cog.config.guild(interaction.guild).is_enabled.set(new_state)

        if new_state:
            button.label = "✅ Automation Enabled"
            button.style = discord.ButtonStyle.success
            await interaction.response.send_message("▶️ Music automation has been **enabled**.", ephemeral=True)
        else:
            button.label = "⏹️ Automation Disabled"
            button.style = discord.ButtonStyle.danger
            await interaction.response.send_message("⏹️ Music automation has been **disabled**.", ephemeral=True)
        
        await interaction.message.edit(view=self)


# --- MAIN COG CLASS ---

class AfterworkAudio(commands.Cog, name="AfterworkAudio"):
    """A dynamic, automated music player system."""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6677889901, force_registration=True)
        self.config.register_guild(
            music_voice_channel_id=None,
            music_text_channel_id=None,
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
        if not text_channel_id or not message_id:
            return

        channel = guild.get_channel(text_channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        await self.config.guild(guild).player_message_id.clear()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        
        guild = member.guild
        if not await self.config.guild(guild).is_enabled():
            return
        
        voice_channel_id = await self.config.guild(guild).music_voice_channel_id()
        if not voice_channel_id:
            return

        if after.channel and after.channel.id == voice_channel_id:
            if len(after.channel.members) == 1:
                await self._cleanup_player(guild)

                text_channel_id = await self.config.guild(guild).music_text_channel_id()
                text_channel = guild.get_channel(text_channel_id)
                if not text_channel:
                    return

                embed = discord.Embed(
                    title="🎵 Music Controls",
                    description="The session has started! Use the buttons below to control the music.",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Session started by {member.display_name}")

                try:
                    player_message = await text_channel.send(embed=embed, view=self.player_view)
                    await player_message.pin(reason="Active Music Session")
                    await self.config.guild(guild).player_message_id.set(player_message.id)
                except discord.Forbidden:
                    log.error(f"Missing permissions in {text_channel.name} for guild {guild.name}")

        if before.channel and before.channel.id == voice_channel_id:
            if not before.channel.members:
                await self._cleanup_player(guild)

    async def _invoke_audio_command(self, interaction: discord.Interaction, command_name: str, *, query: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.followup.send("❌ You must be in a voice channel.", ephemeral=False)
        
        command = self.bot.get_command(command_name)
        if not command:
            return await interaction.followup.send(f"❌ Could not find the `{command_name}` command.", ephemeral=False)

        try:
            ctx = await self.bot.get_context(interaction, cls=commands.Context)
            ctx.author = interaction.user
            
            args = [query] if query else []
            await command.invoke(ctx, *args)
            
            await interaction.followup.send(f"✅ Executed `{command_name}` command.", ephemeral=True)
        except Exception as e:
            log.error(f"Error invoking '{command_name}': {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred.", ephemeral=False)

    @commands.group(name="afterworkaudio")
    @commands.admin_or_permissions(manage_guild=True)
    async def afterworkaudio_group(self, ctx: commands.Context):
        """Manage the AfterworkAudio system."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @afterworkaudio_group.command(name="deploy")
    async def afterworkaudio_deploy(self, ctx: commands.Context):
        """Deploys the persistent settings panel."""
        await self.config.guild(ctx.guild).music_text_channel_id.set(ctx.channel.id)
        
        embed = discord.Embed(
            title="⚙️ Afterwork Audio Settings",
            description=(
                "Use this panel to configure the automated music system for this server.\n\n"
                "1. **Set a Voice Channel**: Choose the VC that will activate the player.\n"
                "2. **Add/Remove Playlists**: Create shortcuts for your favorite playlists.\n"
                "3. **Enable Automation**: Toggle the system on or off."
            ),
            color=await ctx.embed_color()
        )
        
        is_enabled = await self.config.guild(ctx.guild).is_enabled()
        toggle_button = discord.utils.get(self.settings_view.children, custom_id="toggle_automation")
        if is_enabled:
            toggle_button.label = "✅ Automation Enabled"
            toggle_button.style = discord.ButtonStyle.success
        else:
            toggle_button.label = "⏹️ Automation Disabled"
            toggle_button.style = discord.ButtonStyle.danger

        await ctx.send(embed=embed, view=self.settings_view)

async def setup(bot):
    cog = AfterworkAudio(bot)
    await bot.add_cog(cog)

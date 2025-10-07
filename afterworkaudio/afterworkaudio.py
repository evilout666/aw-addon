import discord
from redbot.core import commands, Config
import logging
from typing import Optional
import lavalink
import asyncio

log = logging.getLogger("red.AfterworkAudio")


# --- UTILITY ---

async def _send_owner_dm(bot, message: str):
    """Sends a critical error message directly to the bot owner."""
    owner = bot.get_user(bot.owner_id)
    if owner:
        try:
            embed = discord.Embed(
                title="⚠️ Afterwork Audio Error",
                description=message,
                color=discord.Color.red()
            )
            await owner.send(embed=embed)
        except discord.Forbidden:
            log.error("Failed to DM owner. Owner must enable DMs.")


# --- MODALS ---

class SetVoiceChannelModal(discord.ui.Modal, title="Set Music Channel"):
    channel_id_input = discord.ui.TextInput(label="Voice Channel ID", placeholder="Paste the ID of the music voice channel.", required=True)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        channel_id_str = self.channel_id_input.value.strip()
        try:
            channel_id = int(channel_id_str)
        except ValueError:
            return await interaction.response.send_message("❌ Invalid ID.", ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            return await interaction.response.send_message("❌ Voice channel not found.", ephemeral=True)

        await self.cog.config.guild(interaction.guild).music_voice_channel_id.set(channel.id)
        await interaction.response.defer(ephemeral=True)
        await self.cog.update_settings_message(interaction.guild, interaction.message)


class PlayerPlayModal(discord.ui.Modal, title="Request a Song"):
    query_input = discord.ui.TextInput(label="Song URL or Search Query", placeholder="Paste a URL or type a song name to search.", required=True)

    def __init__(self, cog: commands.Cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        query = self.query_input.value.strip()
        await self.cog._invoke_audio_command(interaction, "play", query=query)


# --- VIEWS ---

class PlayerView(discord.ui.View):
    def __init__(self, cog: commands.Cog, is_playing: bool = False, is_shuffling: bool = False):
        super().__init__(timeout=None)
        self.cog = cog

        song_button = discord.ui.Button(label="Song", style=discord.ButtonStyle.primary, custom_id="player_song")
        song_button.callback = self.on_song
        self.add_item(song_button)

        play_pause_button = discord.ui.Button(
            label="Pause" if is_playing else "Play",
            style=discord.ButtonStyle.success,
            custom_id="player_pause_toggle"
        )
        play_pause_button.callback = self.on_play_pause
        self.add_item(play_pause_button)

        skip_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.success, custom_id="player_skip")
        skip_button.callback = self.on_skip
        self.add_item(skip_button)

        shuffle_button = discord.ui.Button(
            label="Mode",
            style=discord.ButtonStyle.success if is_shuffling else discord.ButtonStyle.secondary,
            custom_id="player_shuffle_toggle"
        )
        shuffle_button.callback = self.on_shuffle
        self.add_item(shuffle_button)

        stop_button = discord.ui.Button(label="Stop", style=discord.ButtonStyle.danger, custom_id="player_stop")
        stop_button.callback = self.on_stop
        self.add_item(stop_button)

    async def on_song(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PlayerPlayModal(self.cog))

    async def on_play_pause(self, interaction: discord.Interaction):
        await self.cog._invoke_audio_command(interaction, "pause")

    async def on_skip(self, interaction: discord.Interaction):
        await self.cog._invoke_audio_command(interaction, "skip")

    async def on_shuffle(self, interaction: discord.Interaction):
        await self.cog._invoke_audio_command(interaction, "shuffle")

    async def on_stop(self, interaction: discord.Interaction):
        await self.cog._invoke_audio_command(interaction, "stop")


class SettingsView(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await self.cog.bot.is_owner(interaction.user):
            return True
        await interaction.response.send_message("Only the bot owner can use these controls.", ephemeral=True)
        return False

    @discord.ui.button(label="Channel ID", style=discord.ButtonStyle.primary, custom_id="set_voice_channel")
    async def set_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetVoiceChannelModal(self.cog))

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
            settings_message_id=None,
            player_message_id=None,
            is_enabled=False,
        )
        self.settings_view = SettingsView(self)
        self.player_view = PlayerView(self)

    async def cog_load(self):
        self.bot.add_view(self.settings_view)
        self.bot.add_view(self.player_view)

    async def _cleanup_player(self, guild: discord.Guild):
        vc_id = await self.config.guild(guild).music_voice_channel_id()
        if not vc_id: return
        
        voice_channel = guild.get_channel(vc_id)
        if not voice_channel: return
        
        message_id = await self.config.guild(guild).player_message_id()
        if not message_id: return

        try:
            message = await voice_channel.fetch_message(message_id)
            await message.delete()
        except (discord.NotFound, discord.Forbidden): pass
        await self.config.guild(guild).player_message_id.clear()

    async def update_settings_message(self, guild: discord.Guild, message: Optional[discord.Message] = None):
        if not message:
            settings_message_id = await self.config.guild(guild).settings_message_id()
            if not settings_message_id: return
            try:
                message = await message.channel.fetch_message(settings_message_id)
            except (discord.NotFound, discord.Forbidden, AttributeError): return

        settings = await self.config.guild(guild).all()
        is_enabled = settings.get('is_enabled', False)
        vc_id = settings.get('music_voice_channel_id')
        
        status_display = "🟢 Active" if is_enabled else "🔴 Inactive"
        vc_display = f"**{guild.get_channel(vc_id).name}** (`{vc_id}`)" if vc_id and guild.get_channel(vc_id) else "*Not configured*"

        embed = message.embeds[0]
        embed.description = "Use this panel to set the music channel. The player will appear in that channel's integrated text chat."
        embed.clear_fields()
        embed.add_field(name="System Status", value=status_display, inline=False)
        embed.add_field(name="Music Channel", value=vc_display, inline=False)
        
        toggle_button = discord.utils.get(self.settings_view.children, custom_id="toggle_automation")
        if is_enabled:
            toggle_button.label = "Disable"
            toggle_button.style = discord.ButtonStyle.danger
        else:
            toggle_button.label = "Enable"
            toggle_button.style = discord.ButtonStyle.success
        
        await message.edit(embed=embed, view=self.settings_view)

    async def _update_player_message(self, guild: discord.Guild):
        player_message_id = await self.config.guild(guild).player_message_id()
        vc_id = await self.config.guild(guild).music_voice_channel_id()
        
        if not player_message_id or not vc_id: return
        channel = guild.get_channel(vc_id)
        if not channel: return
            
        try:
            message = await channel.fetch_message(player_message_id)
            player = lavalink.get_player(guild.id)
            
            is_playing = player and player.is_playing and not player.paused
            is_shuffling = player and player.shuffle

            embed = discord.Embed(title="Music Player", color=discord.Color.green())

            if player and player.current:
                artist = player.current.author.replace("NFrealmusic - ", "").strip()
                title = player.current.title
                if title.lower().startswith(artist.lower()):
                    separator_pos = title.lower().find(artist.lower()) + len(artist)
                    if ' - ' in title[separator_pos:separator_pos+4]:
                         title = title[separator_pos:].lstrip(' -')
                embed.add_field(name="Now Playing", value=f"{artist} - {title}", inline=False)
            
            if player and player.queue:
                tracks_to_show = player.queue[:3]
                queue_list = [f"{i+1}. {track.title}" for i, track in enumerate(tracks_to_show)]
                
                remaining_count = len(player.queue) - len(tracks_to_show)
                if remaining_count > 0:
                    queue_list.append(f"... and {remaining_count} more.")

                if queue_list:
                    embed.add_field(name="Next Song", value="\n".join(queue_list), inline=False)

            if not embed.fields:
                embed.description = "Nothing is playing. Use the 'Song' button to request a track."
            
            new_view = PlayerView(self, is_playing=is_playing, is_shuffling=is_shuffling)
            await message.edit(embed=embed, view=new_view)
        except (discord.NotFound, discord.Forbidden):
            await self.config.guild(guild).player_message_id.clear()

    @commands.Cog.listener("on_red_audio_track_start")
    async def on_track_start(self, guild, track, requester):
        await self._update_player_message(guild)

    @commands.Cog.listener("on_red_audio_track_pause")
    async def on_track_pause(self, guild, track, requester):
        await self._update_player_message(guild)
        
    @commands.Cog.listener("on_red_audio_track_resume")
    async def on_track_resume(self, guild, track, requester):
        await self._update_player_message(guild)

    @commands.Cog.listener("on_red_audio_player_stop")
    async def on_player_stop(self, guild, track, requester):
        await self._update_player_message(guild)
        
    @commands.Cog.listener("on_red_audio_queue_end")
    async def on_queue_end(self, guild, track, requester):
        await self._update_player_message(guild)

    @commands.Cog.listener("on_red_audio_track_add")
    async def on_track_add(self, guild, track, requester):
        await self._update_player_message(guild)

    @commands.Cog.listener("on_red_audio_shuffle_change")
    async def on_shuffle_change(self, guild, shuffle_state):
        await self._update_player_message(guild)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot: return
        guild = member.guild
        if not await self.config.guild(guild).is_enabled(): return
        
        voice_channel_id = await self.config.guild(guild).music_voice_channel_id()
        if not voice_channel_id: return

        if after.channel and after.channel.id == voice_channel_id and len(after.channel.members) == 1:
            voice_channel = after.channel
            await self._cleanup_player(guild)
            embed = discord.Embed(title="Music Player", description="Use the 'Song' button to request a track.", color=discord.Color.green())
            try:
                initial_view = PlayerView(self, is_playing=False, is_shuffling=False)
                player_message = await voice_channel.send(embed=embed, view=initial_view)
                await self.config.guild(guild).player_message_id.set(player_message.id)
            except discord.Forbidden: log.error(f"Missing permissions to send messages in {voice_channel.name}")

        if before.channel and before.channel.id == voice_channel_id and not before.channel.members:
            await self._cleanup_player(guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild: return
        vc_id = await self.config.guild(message.guild).music_voice_channel_id()
        if not vc_id or message.channel.id != vc_id: return

        if message.author.id == self.bot.user.id and message.embeds:
            if message.embeds[0].title == "Music Player":
                return

        player_message_id = await self.config.guild(message.guild).player_message_id()
        if message.id != player_message_id:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound): pass

    async def _invoke_audio_command(self, interaction: discord.Interaction, command_name: str, *, query: str = None):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.voice:
            return await interaction.followup.send("❌ You must be in a voice channel.", ephemeral=True)

        try:
            message = interaction.message
            prefix = (await self.bot.get_prefix(message))[0]
            command_str = f"{prefix}{command_name}"
            if query: command_str += f" {query}"
            
            original_content, message.content = message.content, command_str
            original_author, message.author = message.author, interaction.user
            
            await self.bot.process_commands(message)
            
            message.content = original_content
            message.author = original_author
            
            if command_name in ["pause", "shuffle"]:
                await asyncio.sleep(0.5)
                await self._update_player_message(interaction.guild)

        except Exception as e:
            log.error(f"Error invoking '{command_name}': {e}", exc_info=True)
            await _send_owner_dm(self.bot, f"An error occurred while trying to execute the `{command_name}` command in **{interaction.guild.name}**.")

    @commands.group(name="afterworkaudio")
    @commands.is_owner()
    async def afterworkaudio_group(self, ctx: commands.Context):
        """Manage the AfterworkAudio system."""
        if not ctx.invoked_subcommand: await ctx.send_help()

    @afterworkaudio_group.command(name="deploy")
    async def afterworkaudio_deploy(self, ctx: commands.Context):
        """Deploys the persistent settings panel."""
        settings = await self.config.guild(ctx.guild).all()
        is_enabled = settings.get('is_enabled', False)
        vc_id = settings.get('music_voice_channel_id')
        
        status_display = "🟢 Active" if is_enabled else "🔴 Inactive"
        vc_display = f"**{ctx.guild.get_channel(vc_id).name}** (`{vc_id}`)" if vc_id and ctx.guild.get_channel(vc_id) else "*Not configured*"

        embed = discord.Embed(
            title="Music Channel Control",
            description="Use this panel to set the music channel. The player will appear in that channel's integrated text chat.",
            color=await ctx.embed_color()
        )
        embed.add_field(name="System Status", value=status_display, inline=False)
        embed.add_field(name="Music Channel", value=vc_display, inline=False)
        
        toggle_button = discord.utils.get(self.settings_view.children, custom_id="toggle_automation")
        if is_enabled:
            toggle_button.label = "Disable"
            toggle_button.style = discord.ButtonStyle.danger
        else:
            toggle_button.label = "Enable"
            toggle_button.style = discord.ButtonStyle.success

        msg = await ctx.send(embed=embed, view=self.settings_view)
        await self.config.guild(ctx.guild).settings_message_id.set(msg.id)
        
        try:
            await msg.pin(reason="Afterwork Audio Control Panel")
        except discord.Forbidden:
            log.warning(f"Could not pin the settings message in {ctx.channel.name}.")
        
        try:
            await ctx.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        
        await asyncio.sleep(1)
        try:
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception:
            pass

async def setup(bot):
    cog = AfterworkAudio(bot)
    await bot.add_cog(cog)

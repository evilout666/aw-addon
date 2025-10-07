import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime
from typing import Union

log = logging.getLogger("red.AfterworkAudio")

# --- UTILITY FUNCTIONS ---

def _get_admin_footer(obj: Union[commands.Context, discord.Interaction], status_action: str) -> str:
    """
    Helper to generate the administrative footer format.
    Handles both Context (from commands) and Interaction (from buttons/modals).
    """
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, commands.Context):
        user_display_name = obj.author.display_name
    else:
        user_display_name = obj.user.display_name
    return f"e.Network | {status_action} by {user_display_name} {current_time}"

async def _send_owner_dm(bot, message: str):
    """Sends a critical error message directly to the bot owner."""
    owner = bot.get_user(bot.owner_id)
    if owner:
        try:
            embed = discord.Embed(title="⚠️ Afterwork Audio Error", description=message, color=discord.Color.red())
            await owner.send(embed=embed)
        except discord.Forbidden:
            log.error("Failed to DM owner. Owner must enable DMs.")

# --- MODAL FOR PLAYING MUSIC ---

class PlayModal(discord.ui.Modal, title="Play Music (URL or Search)"):
    source_input = discord.ui.TextInput(
        label="URL or Search Query",
        style=discord.TextStyle.short,
        placeholder="Paste a YouTube/Spotify URL or type a search query.",
        required=True,
        max_length=200,
    )

    def __init__(self, cog: commands.Cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        query = self.source_input.value.strip()
        await interaction.response.defer(ephemeral=True, thinking=True)

        audio_cog = self.cog.bot.get_cog("Audio")
        if not audio_cog:
            return await interaction.followup.send("❌ Audio cog is not loaded.", ephemeral=False)

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.followup.send("❌ You must be in a voice channel to play music.", ephemeral=False)

        try:
            message = await interaction.channel.fetch_message(interaction.message.id)
            ctx = await self.cog.bot.get_context(message)
            ctx.author = interaction.user
            
            play_command = self.cog.bot.get_command("play")
            if not play_command:
                return await interaction.followup.send("❌ Could not find the `play` command.", ephemeral=False)

            await play_command(ctx, query=query)
            await interaction.followup.send(f"✅ Queued up: `{query}`.", ephemeral=True)
            
        except Exception as e:
            log.error(f"Error during play command invocation: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to execute play command.", ephemeral=False)

# --- AUDIO CONTROL VIEW ---

class AudioControls(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def _invoke_audio_command(self, interaction: discord.Interaction, command_name: str):
        await interaction.response.defer(ephemeral=True, thinking=True)

        audio_cog = self.cog.bot.get_cog("Audio")
        if not audio_cog:
            return await interaction.followup.send("❌ Audio cog is not loaded.", ephemeral=False)

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.followup.send("❌ You must be in a voice channel to control playback.", ephemeral=False)
        
        try:
            message = await interaction.channel.fetch_message(interaction.message.id)
            ctx = await self.cog.bot.get_context(message)
            ctx.author = interaction.user

            command_obj = self.cog.bot.get_command(command_name)
            if not command_obj:
                 return await interaction.followup.send(f"❌ Command `{command_name}` not found.", ephemeral=False)
            
            await command_obj(ctx)
            await interaction.followup.send(f"✅ Executed `{command_name}` command.", ephemeral=True)
            
        except Exception as e:
            log.error(f"Error during audio command invocation ({command_name}): {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to execute command.", ephemeral=False)

    @discord.ui.button(label="Play/Search", style=discord.ButtonStyle.success, custom_id="audio_play_url")
    async def play_url_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("❌ You must be in a voice channel to play music.", ephemeral=False)
        await interaction.response.send_modal(PlayModal(self.cog))

    @discord.ui.button(label="Pause/Resume", style=discord.ButtonStyle.blurple, custom_id="audio_pause")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._invoke_audio_command(interaction, "pause")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary, custom_id="audio_skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._invoke_audio_command(interaction, "skip")
        
    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, custom_id="audio_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._invoke_audio_command(interaction, "stop")

# --- MAIN COG CLASS ---

class AfterworkAudio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6677889900, force_registration=True)
        self.config.register_guild(
            setup_message_id=None,
            now_playing_message_id=None
        )

    async def initialize(self):
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                self.bot.add_view(AudioControls(self), message_id=data['setup_message_id'])

    @commands.group(name="afterworkaudio")
    @commands.is_owner()
    async def afterworkaudio_group(self, ctx: commands.Context):
        """Management commands for the AfterworkAudio cog."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @afterworkaudio_group.command(name="deploy")
    async def afterworkaudio_deploy(self, ctx: commands.Context):
        """Deploys the persistent audio control panel."""
        if not self.bot.get_cog("Audio"):
            return await ctx.send("❌ The official Red `Audio` cog must be loaded to use this command.")

        bot_member = ctx.guild.me
        if not ctx.channel.permissions_for(bot_member).manage_messages:
            return await _send_owner_dm(self.bot, f"Config failed in **{ctx.guild.name}**. Need Send/Manage Messages in **#{ctx.channel.name}**.")

        # Cleanup old messages
        old_setup_id = await self.config.guild(ctx.guild).setup_message_id()
        if old_setup_id:
            try:
                await ctx.channel.fetch_message(old_setup_id).delete()
            except discord.HTTPException: pass
        
        old_np_id = await self.config.guild(ctx.guild).now_playing_message_id()
        if old_np_id:
            try:
                await ctx.channel.fetch_message(old_np_id).delete()
            except discord.HTTPException: pass
        
        embed = discord.Embed(
            title="Music Player",
            description="Use these buttons to control music playback.",
            color=await ctx.embed_color()
        )
        embed.set_footer(text=_get_admin_footer(ctx, "Audio Control Hub Deployed"))
        
        view = AudioControls(self)
        sent_message = await ctx.send(embed=embed, view=view)
        
        await sent_message.pin(reason="Afterwork Audio Control Hub.")
        await self.config.guild(ctx.guild).setup_message_id.set(sent_message.id)
        
        await ctx.message.delete()
        await asyncio.sleep(1)
        try:
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception: pass

    # --- AUDIO EVENT LISTENERS ---

    @commands.Cog.listener()
    async def on_red_audio_track_start(self, guild: discord.Guild, track, requester: discord.Member):
        """Event listener for when a new track starts playing."""
        setup_message_id = await self.config.guild(guild).setup_message_id()
        if not setup_message_id:
            return

        try:
            # We need the channel where the hub is located
            hub_message = await self.bot.http.get_message(self.bot.get_channel_for_message_id(setup_message_id), setup_message_id)
            channel = self.bot.get_channel(hub_message['channel_id'])
            if not channel: return
        except (discord.NotFound, discord.Forbidden):
            return

        np_embed = discord.Embed(
            title=track.title,
            description=f"by {track.author}",
            color=await self.bot.get_embed_color(channel)
        )
        if track.thumbnail:
            np_embed.set_thumbnail(url=track.thumbnail)
        
        np_message_id = await self.config.guild(guild).now_playing_message_id()
        
        try:
            if np_message_id:
                # Edit the existing "Now Playing" message
                np_message = await channel.fetch_message(np_message_id)
                await np_message.edit(embed=np_embed)
            else:
                # Post a new "Now Playing" message
                new_np_message = await channel.send(embed=np_embed)
                await self.config.guild(guild).now_playing_message_id.set(new_np_message.id)
        except (discord.NotFound, discord.Forbidden):
            # If message was deleted, post a new one
            new_np_message = await channel.send(embed=np_embed)
            await self.config.guild(guild).now_playing_message_id.set(new_np_message.id)
        except Exception as e:
            log.error(f"Error updating Now Playing message: {e}", exc_info=True)


    @commands.Cog.listener()
    async def on_red_audio_queue_end(self, guild: discord.Guild, track, requester: discord.Member):
        """Event listener for when the queue finishes."""
        await self._cleanup_now_playing(guild)

    @commands.Cog.listener()
    async def on_red_audio_player_stop(self, guild: discord.Guild, track):
        """Event listener for when the player is stopped manually."""
        await self._cleanup_now_playing(guild)
        
    async def _cleanup_now_playing(self, guild: discord.Guild):
        """Helper to delete the 'Now Playing' message."""
        np_message_id = await self.config.guild(guild).now_playing_message_id()
        setup_message_id = await self.config.guild(guild).setup_message_id()

        if np_message_id and setup_message_id:
            try:
                hub_message = await self.bot.http.get_message(self.bot.get_channel_for_message_id(setup_message_id), setup_message_id)
                channel = self.bot.get_channel(hub_message['channel_id'])
                if channel:
                    message = await channel.fetch_message(np_message_id)
                    await message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass # Message already gone or permissions lost
            finally:
                await self.config.guild(guild).now_playing_message_id.set(None)


async def setup(bot):
    cog = AfterworkAudio(bot)
    await cog.initialize()
    await bot.add_cog(cog)


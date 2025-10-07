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
    
    # This `isinstance` check is the specific fix for your error.
    # It correctly uses .author for commands and .user for interactions.
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
        # Use the robust command invocation helper from the main cog class
        await self.cog._invoke_audio_command(interaction, "play", query=query)


# --- AUDIO CONTROL VIEW ---

class AudioControls(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Play/Search", style=discord.ButtonStyle.success, custom_id="audio_play_url")
    async def play_url_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("❌ You must be in a voice channel to play music.", ephemeral=True)
        await interaction.response.send_modal(PlayModal(self.cog))

    @discord.ui.button(label="Pause/Resume", style=discord.ButtonStyle.blurple, custom_id="audio_pause")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._invoke_audio_command(interaction, "pause")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary, custom_id="audio_skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._invoke_audio_command(interaction, "skip")
        
    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, custom_id="audio_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._invoke_audio_command(interaction, "stop")

# --- MAIN COG CLASS ---

class AfterworkAudio(commands.Cog, name="AfterworkAudio"):
    """
    Provides a persistent, button-based control panel for Red's official Audio cog.
    """
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6677889900, force_registration=True)
        self.config.register_guild(setup_message_id=None)
        self.view = AudioControls(self) # Keep a reference to the view

    async def cog_load(self):
        """Cog load logic. Re-registers the persistent view."""
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                self.bot.add_view(self.view, message_id=data['setup_message_id'])

    def cog_unload(self):
        """Cog unload logic. Stops the persistent view."""
        self.view.stop()

    async def _invoke_audio_command(self, interaction: discord.Interaction, command_name: str, *, query: str = None):
        """More robust helper to invoke Audio commands directly."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        audio_cog = self.bot.get_cog("Audio")
        if not audio_cog:
            return await interaction.followup.send("❌ Audio cog is not loaded.", ephemeral=False)

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.followup.send("❌ You must be in a voice channel.", ephemeral=False)
        
        command = self.bot.get_command(command_name)
        if not command:
            log.error(f"Could not find the '{command_name}' command in the Audio cog.")
            return await interaction.followup.send(f"❌ Could not find the `{command_name}` command.", ephemeral=False)

        try:
            ctx = await self.bot.get_context(interaction, cls=commands.Context)
            ctx.author = interaction.user
            ctx.voice_client = interaction.guild.voice_client

            args = [query] if query else []
            await command.invoke(ctx, *args)
            
            await interaction.followup.send(f"✅ Executed `{command_name}` command.", ephemeral=True)
        except Exception as e:
            log.error(f"Error invoking '{command_name}' from AfterworkAudio: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while executing the command.", ephemeral=False)

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
            await _send_owner_dm(self.bot, f"Config failed in **{ctx.guild.name}**. Need Send/Manage Messages in **#{ctx.channel.name}**.")
            return await ctx.send("❌ I lack the `Manage Messages` permission in this channel.", ephemeral=True)

        old_message_id = await self.config.guild(ctx.guild).setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException:
                pass
        
        embed = discord.Embed(
            title="Music Player",
            description="Use these buttons to control music playback in the server.",
            color=await ctx.embed_color()
        )
        embed.add_field(
            name="⚠️ Important",
            value="This panel requires the main `Audio` cog to be fully configured. For services like Spotify, you must set the appropriate API keys in Red's global settings (`[p]audioset spotifyapi`).",
            inline=False
        )
        embed.set_footer(text=_get_admin_footer(ctx, "Audio Control Hub Deployed"))
        
        sent_message = await ctx.send(embed=embed, view=self.view)
        
        try:
            await sent_message.pin(reason="Afterwork Audio Control Hub.")
        except discord.Forbidden:
            await ctx.send("⚠️ I couldn't pin the message. Please ensure I have the `Manage Messages` permission.", ephemeral=True, delete_after=15)
        
        await self.config.guild(ctx.guild).setup_message_id.set(sent_message.id)
        
        await ctx.message.delete()
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

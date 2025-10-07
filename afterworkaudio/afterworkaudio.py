import discord
from redbot.core import commands
import logging

log = logging.getLogger("red.AfterworkAudio")

# --- MODAL FOR PLAYING MUSIC ---

class PlayModal(discord.ui.Modal, title="Play Music (URL or Search)"):
    """Modal to collect the song source (URL or search term)."""
    
    source_input = discord.ui.TextInput(
        label="URL or Search Query",
        style=discord.TextStyle.short,
        placeholder="Paste a YouTube/Spotify URL or type a search query.",
        required=True,
        max_length=200,
    )

    def __init__(self, cog: commands.Cog, prefix: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.prefix = prefix

    async def on_submit(self, interaction: discord.Interaction):
        query = self.source_input.value.strip()
        command_name = "play"
        
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self.cog.bot.get_cog("Audio"):
            return await interaction.followup.send("❌ Audio cog is not loaded.", ephemeral=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.followup.send("❌ You must be in a voice channel to play music.", ephemeral=True)

        # Execute the [p]play command
        try:
            await self.cog.bot.process_commands_from_text(
                f"{self.prefix}{command_name} {query}", 
                interaction.message.channel, 
                interaction.user
            )
            await interaction.followup.send(f"✅ Executed `{self.prefix}play` with query: `{query}`. Check your voice channel for status.", ephemeral=True)
            
        except Exception as e:
            log.error(f"Error during play command invocation: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to execute command. Error: {e.__class__.__name__}", ephemeral=True)


# --- AUDIO CONTROL VIEW ---

class AudioControls(discord.ui.View):
    """
    Persistent view containing buttons to control Red's Audio cog functions.
    """
    def __init__(self, cog: commands.Cog, prefix: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.prefix = prefix
        self.audio_cog = cog.bot.get_cog("Audio")

        # Disable command buttons if the Audio cog isn't found
        if not self.audio_cog:
            log.error("Red Audio cog not found. Cannot guarantee button functionality.")

    async def _invoke_audio_command(self, interaction: discord.Interaction, command_name: str):
        """
        Helper to invoke a command from the Audio cog using a custom context.
        """
        # Defer immediately to prevent interaction token expiry
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self.audio_cog:
            return await interaction.followup.send("❌ Audio cog is not loaded.", ephemeral=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.followup.send("❌ You must be in a voice channel to control playback.", ephemeral=True)

        # Execute the command
        try:
            await self.cog.bot.process_commands_from_text(
                f"{self.prefix}{command_name}", 
                interaction.message.channel, 
                interaction.user
            )
            await interaction.followup.send(f"✅ Executed `{self.prefix}{command_name}`.", ephemeral=True)
            
        except Exception as e:
            log.error(f"Error during audio command invocation ({command_name}): {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to execute command. Error: {e.__class__.__name__}", ephemeral=True)

    @discord.ui.button(label="Play URL/Search", style=discord.ButtonStyle.success, custom_id="audio_play_url")
    async def play_url_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to launch the Modal for playing music."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("❌ You must be in a voice channel to play music.", ephemeral=True)

        modal = PlayModal(self.cog, self.prefix)
        await interaction.response.send_modal(modal)

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
    """
    Provides persistent buttons for controlling the Red Audio cog.
    """
    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        log.info("AfterworkAudio unloaded.")
        
    @commands.command(name="awaudio")
    @commands.is_owner()
    async def awaudio_command(self, ctx: commands.Context):
        """
        Posts the persistent audio control panel.
        Requires Red's built-in Audio cog to be loaded.
        """
        
        audio_cog = self.bot.get_cog("Audio")
        if not audio_cog:
            return await ctx.send("❌ The official Red `Audio` cog must be loaded to use this command.")

        # Get the bot's current prefix for command invocation
        prefix_list = await self.bot.get_prefixes(ctx.message)
        prefix = prefix_list[0] if prefix_list else "!"

        embed = discord.Embed(
            title="🎶 Music Control Panel",
            description=f"Use these buttons to control playback. Prefix for commands: `{prefix}`",
            color=await ctx.embed_color()
        )
        
        view = AudioControls(self, prefix)
        
        sent_message = await ctx.send(embed=embed, view=view)

        await ctx.message.delete()


async def setup(bot):
    """The function Red uses to load the cog."""
    cog = AfterworkAudio(bot)
    await bot.add_cog(cog)

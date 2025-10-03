import discord
from redbot.core import commands
import json
import logging

log = logging.getLogger("red.AfterworkEmbed")

# --- MODAL (The Pop-up Box for JSON Input) ---

class EmbedJSONModal(discord.ui.Modal, title="Embed JSON Input"):
    """A Modal with a large text box for multi-line JSON."""
    
    json_input = discord.ui.TextInput(
        label="JSON Data",
        style=discord.TextStyle.long,  # Use 'long' for a multi-line paragraph box
        placeholder='e.g., {"title": "Hello", "description": "This is a test."}',
        required=True,
    )

    def __init__(self, target_channel: discord.TextChannel):
        super().__init__(timeout=600)  # 10-minute timeout
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction):
        """Handles the submission of the modal."""
        json_data = self.json_input.value
        
        try:
            # Validate and convert the JSON data
            embed_data = json.loads(json_data)
            if not isinstance(embed_data, dict):
                return await interaction.response.send_message(
                    "❌ **Error:** The provided JSON must be an object (starts with `{` and ends with `}`).",
                    ephemeral=True
                )
            
            embed = discord.Embed.from_dict(embed_data)
            
            # Send the embed to the target channel
            await self.target_channel.send(embed=embed)
            
            # Send a private confirmation message
            await interaction.response.send_message(
                f"✅ Embed successfully sent to {self.target_channel.mention}.",
                ephemeral=True
            )

        except json.JSONDecodeError as e:
            await interaction.response.send_message(
                f"❌ **JSON Error:** Failed to parse the JSON data. Please check for syntax errors like missing commas or quotes.\n`{e}`",
                ephemeral=True
            )
        except Exception as e:
            # Catches other discord.py errors, like invalid embed structures
            await interaction.response.send_message(
                f"❌ **Embed Error:** An error occurred while creating the embed. This could be due to an invalid field or structure.\n`{e}`",
                ephemeral=True
            )

# --- MAIN COG CLASS ---

class AfterworkEmbed(commands.Cog, name="AfterworkEmbed"):
    """
    A secure, owner-only utility to send custom embeds from JSON via a Modal.
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="afterworkembed")
    @commands.is_owner()
    async def afterwork_embed_command(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Opens a pop-up box to send a JSON-defined embed to a channel.
        """
        # Launch the Modal for the user to input their JSON
        modal = EmbedJSONModal(target_channel=channel)
        await ctx.send_modal(modal)
        
        # Clean up the command invocation
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass # Ignore if permissions are missing, as the command is owner-only

async def setup(bot):
    """The function Red uses to load the cog."""
    await bot.add_cog(AfterworkEmbed(bot))

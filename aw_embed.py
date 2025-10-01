import discord
from redbot.core import commands, Config
import json
import logging

log = logging.getLogger("red.afterwork.embed")

class AfterWorkEmbed(commands.Cog, name="AfterWorkEmbed"):
    """
    Embed commands for Afterwork.
    """
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=123456789, force_registration=True)

    @commands.command(name="awembed")
    async def embed(self, ctx: commands.Context, channel: discord.TextChannel, *, data: str):
        """
        Sends a custom embed message to a specified channel.
        
        Example: !afterwork embed #general {"title": "Hello", "description": "World"}
        """
        try:
            embed_data = json.loads(data)
            embed = discord.Embed.from_dict(embed_data)
            
            if not embed_data:
                await ctx.send("Error: The embed data is empty. Please provide a valid JSON object.")
                return

            await channel.send(embed=embed)
            await ctx.send(f"Embed successfully sent to {channel.mention}.")
        except json.JSONDecodeError:
            await ctx.send("Error: Invalid JSON format. Please check your data.")
        except discord.errors.Forbidden:
            await ctx.send("I don't have permission to send messages in that channel.")
        except discord.HTTPException as e:
            await ctx.send(f"Error: Discord was unable to process the embed. This might be due to incorrect data (e.g., a bad URL). Details: `{e}`")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {e}")

async def setup(bot):
    aw_embed_cog = AfterWorkEmbed(bot)
    await bot.add_cog(aw_embed_cog)

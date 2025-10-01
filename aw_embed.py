import discord
from redbot.core import commands
import json
import logging

log = logging.getLogger("red.awcogs.aw_embed")

class AWEmbed(commands.Cog):
    """Send custom embeds (development)."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="aw_embed")
    async def aw_embed(self, ctx: commands.Context, channel: discord.TextChannel, *, data: str):
        """Send a JSON-defined embed to a channel.

        Example: [p]aw_embed #general {"title": "Hi", "description": "World"}
        """
        try:
            embed_data = json.loads(data)
            if not isinstance(embed_data, dict):
                await ctx.send("JSON must be an object.")
                return
            embed = discord.Embed.from_dict(embed_data)
            await channel.send(embed=embed)
            await ctx.send(f"Sent to {channel.mention}.")
        except json.JSONDecodeError:
            await ctx.send("Bad JSON.")
        except Exception as e:
            await ctx.send(f"Error: {e}")

async def setup(bot):
    await bot.add_cog(AWEmbed(bot))

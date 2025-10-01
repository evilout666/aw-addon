import discord
from redbot.core import commands

class AWVoice(commands.Cog):
    """Minimal voice helper (no config, no logging)."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="aw_voice_test")
    async def aw_voice_test(self, ctx: commands.Context):
        """Test command."""
        await ctx.send("aw_voice loaded!")

async def setup(bot):
    await bot.add_cog(AWVoice(bot))

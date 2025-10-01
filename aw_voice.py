import discord
from redbot.core import commands, Config
import logging

log = logging.getLogger("red.awcogs.aw_voice")

class AWVoice(commands.Cog):
    """Minimal voice helper (stripped for load debug)."""
    def __init__(self, bot):
        self.bot = bot
        # Use a different identifier to avoid any stale config schema issues
        self.config = Config.get_conf(self, identifier=22334455, force_registration=True)
        self.config.register_guild(
            embed_color=0x4287f5,
            embed_description="Welcome, {user.mention}! Your new channel, {channel.name}, is ready to use."
        )

    @commands.command(name="aw_voice_status")
    async def aw_voice_status(self, ctx: commands.Context):
        """Show minimal stored settings (debug)."""
        data = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(
            title="aw_voice status (minimal)",
            description=data['embed_description'],
            color=data['embed_color']
        )
        await ctx.send(embed=embed)

    @commands.command(name="aw_voice_setdesc")
    async def aw_voice_setdesc(self, ctx: commands.Context, *, description: str):
        """Set description template."""
        await self.config.guild(ctx.guild).embed_description.set(description)
        await ctx.tick()

    @commands.command(name="aw_voice_preview")
    async def aw_voice_preview(self, ctx: commands.Context):
        tpl = await self.config.guild(ctx.guild).embed_description()
        resolved = tpl.replace('{user.mention}', ctx.author.mention).replace('{channel.name}', 'Example Channel')
        color = await self.config.guild(ctx.guild).embed_color()
        embed = discord.Embed(title="Preview", description=resolved, color=color)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AWVoice(bot))

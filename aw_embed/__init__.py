from .aw_embed import AWEmbed

async def setup(bot):
    await bot.add_cog(AWEmbed(bot))

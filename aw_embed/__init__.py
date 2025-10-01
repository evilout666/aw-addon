from .aw_embed import AwEmbed

async def setup(bot):
    await bot.add_cog(AwEmbed(bot))

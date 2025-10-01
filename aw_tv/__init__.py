from .aw_tv import AwTV

async def setup(bot):
    await bot.add_cog(AwTV(bot))

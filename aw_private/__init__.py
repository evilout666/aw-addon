from .aw_private import AwPrivate

async def setup(bot):
    await bot.add_cog(AwPrivate(bot))

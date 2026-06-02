from .afterwork import Afterwork

async def setup(bot):
    cog = Afterwork(bot)
    await cog.initialize()
    await bot.add_cog(cog)

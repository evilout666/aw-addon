from .afterworktv import AfterworkTV

async def setup(bot):
    cog = AfterworkTV(bot)
    await cog.initialize()
    await bot.add_cog(cog)

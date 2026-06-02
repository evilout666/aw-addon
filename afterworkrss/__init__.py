from .afterworkrss import AfterworkRSS

async def setup(bot):
    cog = AfterworkRSS(bot)
    await cog.initialize()
    await bot.add_cog(cog)

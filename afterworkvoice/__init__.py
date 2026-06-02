from .afterworkvoice import AfterworkVoice

async def setup(bot):
    cog = AfterworkVoice(bot)
    await cog.initialize()
    await bot.add_cog(cog)

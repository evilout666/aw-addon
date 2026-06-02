from .afterworkaudio import AfterworkAudio

async def setup(bot):
    cog = AfterworkAudio(bot)
    await bot.add_cog(cog)

from .afterworkembed import AfterworkEmbed

async def setup(bot):
    cog = AfterworkEmbed(bot)
    await cog.initialize()
    await bot.add_cog(cog)

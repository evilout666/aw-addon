from .AfterWork import AfterWork

async def setup(bot):
    await bot.add_cog(AfterWork(bot))

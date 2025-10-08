from .afterworkamp import AfterworkAMP

async def setup(bot):
    await bot.add_cog(AfterworkAMP(bot))

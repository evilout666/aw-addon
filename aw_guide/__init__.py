from .aw_guide import AWGuide

async def setup(bot):
    await bot.add_cog(AWGuide(bot))

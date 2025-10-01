from .aw_voice import AWVoice

async def setup(bot):
    await bot.add_cog(AWVoice(bot))

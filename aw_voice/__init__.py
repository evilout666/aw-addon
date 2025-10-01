from .aw_voice import AwVoice

async def setup(bot):
    await bot.add_cog(AwVoice(bot))

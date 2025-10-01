from .aw_permissions import AwPermissions

async def setup(bot):
    await bot.add_cog(AwPermissions(bot))

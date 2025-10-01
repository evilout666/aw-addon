import discord
from redbot.core import commands, Config, checks
import logging

log = logging.getLogger("red.awcogs.aw_voice")

class AWVoice(commands.Cog):
    """Voice channel helper (development)."""
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=123456789, force_registration=True)
        self.config.register_guild(
            source_id=None,
            category_id=None,
            create_text_channels=False,
            embed_color=0x4287f5,
            embed_description="Welcome, {user.mention}! Your new channel, {channel.name}, is ready to use.",
            room_channels={}
        )

    @commands.group(name="aw_voice")
    @checks.admin_or_permissions(manage_guild=True)
    async def aw_voice_settings(self, ctx: commands.Context):
        """Voice channel announcer settings."""
        pass

    @aw_voice_settings.command(name="setsource")
    async def set_source(self, ctx: commands.Context, source_channel: discord.VoiceChannel, category: discord.CategoryChannel):
        await self.config.guild(ctx.guild).source_id.set(source_channel.id)
        await self.config.guild(ctx.guild).category_id.set(category.id)
        await ctx.send(f"Source voice channel **{source_channel.name}**, category **{category.name}**.")

    @aw_voice_settings.command(name="toggle")
    async def toggle_text_channels(self, ctx: commands.Context):
        current = await self.config.guild(ctx.guild).create_text_channels()
        new = not current
        await self.config.guild(ctx.guild).create_text_channels.set(new)
        await ctx.send(f"Private text channel creation **{'enabled' if new else 'disabled'}**.")

    @aw_voice_settings.command(name="setcolor")
    async def set_color(self, ctx: commands.Context, color: str):
        try:
            value = int(color.replace('#', ''), 16)
        except ValueError:
            await ctx.send("Invalid hex color.")
            return
        await self.config.guild(ctx.guild).embed_color.set(value)
        await ctx.send(f"Color set to `#{value:06X}`")

    @aw_voice_settings.command(name="setdescription")
    async def set_description(self, ctx: commands.Context, *, description: str):
        await self.config.guild(ctx.guild).embed_description.set(description)
        await ctx.send("Description updated.")

    @aw_voice_settings.command(name="status")
    async def status(self, ctx: commands.Context):
        data = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(
            title="aw_voice status",
            description=data['embed_description'],
            color=data['embed_color']
        )
        embed.add_field(name="Source", value=str(data.get('source_id')), inline=False)
        embed.add_field(name="Category", value=str(data.get('category_id')), inline=False)
        embed.add_field(name="Create Text", value=str(data.get('create_text_channels')), inline=False)
        await ctx.send(embed=embed)

    @aw_voice_settings.command(name="preview")
    async def preview(self, ctx: commands.Context):
        desc = (await self.config.guild(ctx.guild).embed_description())
        desc = desc.replace('{user.mention}', ctx.author.mention).replace('{channel.name}', 'Example Channel')
        color = await self.config.guild(ctx.guild).embed_color()
        embed = discord.Embed(title="Preview", description=desc, color=color)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AWVoice(bot))

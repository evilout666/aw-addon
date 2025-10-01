import discord
from redbot.core import commands, Config, checks
import logging

log = logging.getLogger("red.awcogs.aw_voice")

class AWVoice(commands.Cog):
    """Voice channel helper."""
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
        await ctx.send(f"Source voice channel set to **{source_channel.name}** and category to **{category.name}**.")

    @aw_voice_settings.command(name="toggle")
    async def toggle_text_channels(self, ctx: commands.Context):
        current = await self.config.guild(ctx.guild).create_text_channels()
        new = not current
        await self.config.guild(ctx.guild).create_text_channels.set(new)
        status = "enabled" if new else "disabled"
        await ctx.send(f"Private text channel creation has been **{status}**.")

    @aw_voice_settings.command(name="setcolor")
    async def set_color(self, ctx: commands.Context, color: str):
        try:
            color_int = int(color.replace("#", ""), 16)
            await self.config.guild(ctx.guild).embed_color.set(color_int)
            await ctx.send(f"Embed color set to `{color}`.")
        except ValueError:
            await ctx.send("Invalid color. Please use a hex code (e.g., `#00FFFF`).")

    @aw_voice_settings.command(name="setdescription")
    async def set_description(self, ctx: commands.Context, *, description: str):
        await self.config.guild(ctx.guild).embed_description.set(description)
        await ctx.send("Embed description updated.")

    @aw_voice_settings.command(name="status")
    async def show_status(self, ctx: commands.Context):
        settings = await self.config.guild(ctx.guild).all()
        source_channel = self.bot.get_channel(settings['source_id']) if settings['source_id'] else None
        category = self.bot.get_channel(settings['category_id']) if settings['category_id'] else None
        source_name = source_channel.mention if source_channel else "Not set"
        category_name = category.mention if category else "Not set"
        text_channel_status = "Enabled" if settings['create_text_channels'] else "Disabled"
        embed = discord.Embed(
            title="Voice Channel Announcer Status",
            description="Here's the current configuration for the voice channel announcements.",
            color=settings['embed_color']
        )
        embed.add_field(name="Source Channel", value=source_name, inline=False)
        embed.add_field(name="Channel Category", value=category_name, inline=False)
        embed.add_field(name="Text Channel Creation", value=text_channel_status, inline=False)
        embed.add_field(name="Embed Description", value=settings['embed_description'], inline=False)
        embed.add_field(name="Embed Color", value=f"#{settings['embed_color']:06X}", inline=False)
        await ctx.send(embed=embed)

    @aw_voice_settings.command(name="preview")
    async def preview_message(self, ctx: commands.Context):
        description = await self.config.guild(ctx.guild).embed_description()
        color = await self.config.guild(ctx.guild).embed_color()
        description = description.replace("{user.mention}", ctx.author.mention)
        description = description.replace("{channel.name}", "Example Channel")
        embed = discord.Embed(
            title="Welcome to your new room!",
            description=description,
            color=color
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AWVoice(bot))

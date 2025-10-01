import discord
from redbot.core import commands, Config, checks
import logging

log = logging.getLogger("red.awcogs.aw_tv")

class AWTV(commands.Cog):
    """Sonarr/Radarr webhook formatter (development)."""
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)
        self.config.register_guild(source_channel=None, dest_channel=None, enabled=True)

    @commands.group(name="aw_tv")
    @checks.admin_or_permissions(manage_guild=True)
    async def aw_tv_settings(self, ctx: commands.Context):
        """Settings for webhook repost."""
        pass

    @aw_tv_settings.command(name="channel")
    async def set_channels(self, ctx: commands.Context, source: discord.TextChannel, destination: discord.TextChannel):
        await self.config.guild(ctx.guild).source_channel.set(source.id)
        await self.config.guild(ctx.guild).dest_channel.set(destination.id)
        await ctx.send(f"Source set to {source.mention}. Destination {destination.mention}.")

    @aw_tv_settings.command(name="toggle")
    async def toggle_posting(self, ctx: commands.Context):
        state = await self.config.guild(ctx.guild).enabled()
        new = not state
        await self.config.guild(ctx.guild).enabled.set(new)
        await ctx.send(f"Webhook repost now {'enabled' if new else 'disabled'}.")

    @aw_tv_settings.command(name="status")
    async def show_status(self, ctx: commands.Context):
        data = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(title="aw_tv status", color=await ctx.embed_color())
        embed.add_field(name="Enabled", value=str(data.get('enabled')), inline=False)
        embed.add_field(name="Source", value=str(data.get('source_channel')), inline=False)
        embed.add_field(name="Destination", value=str(data.get('dest_channel')), inline=False)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not message.embeds:
            return
        if message.author.bot is False:
            return
        data = await self.config.guild(message.guild).all()
        if not data.get('enabled') or message.channel.id != data.get('source_channel'):
            return
        dest_id = data.get('dest_channel')
        if not dest_id:
            return
        dest = self.bot.get_channel(dest_id)
        if not dest:
            return
        for emb in message.embeds:
            try:
                footer = (emb.footer.text or "") if emb.footer else ""
            except Exception:
                footer = ""
            if any(tag in footer for tag in ("Sonarr", "Radarr")):
                new = discord.Embed(title=emb.title, description=emb.description, color=emb.color)
                if emb.thumbnail:
                    new.set_thumbnail(url=emb.thumbnail.url)
                try:
                    await dest.send(embed=new)
                except Exception:
                    log.exception("Failed to forward embed")

async def setup(bot):
    await bot.add_cog(AWTV(bot))

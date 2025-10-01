import discord
from redbot.core import commands, Config, checks
import logging

log = logging.getLogger("red.awcogs.aw_tv")

class AWTV(commands.Cog):
    """
    Sonarr/Radarr Webhook handler.
    """
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)
        self.config.register_guild(
            source_channel=None,
            dest_channel=None,
            enabled=True
        )

    @commands.group(name="aw_tv")
    @checks.admin_or_permissions(manage_guild=True)
    async def aw_tv_settings(self, ctx: commands.Context):
        """
        Settings for the Sonarr/Radarr webhook cog.
        """
        pass

    @aw_tv_settings.command(name="channel")
    async def set_channels(self, ctx: commands.Context, source: discord.TextChannel, destination: discord.TextChannel):
        """
        Set the source channel for webhooks and the destination for formatted posts.
        """
        await self.config.guild(ctx.guild).source_channel.set(source.id)
        await self.config.guild(ctx.guild).dest_channel.set(destination.id)
        await ctx.send(
            f"Webhook source channel set to {source.mention}.\n"
            f"Formatted posts will be sent to {destination.mention}."
        )

    @aw_tv_settings.command(name="toggle")
    async def toggle_posting(self, ctx: commands.Context):
        """
        Enable or disable automatic posting of formatted embeds.
        """
        current_state = await self.config.guild(ctx.guild).enabled()
        new_state = not current_state
        await self.config.guild(ctx.guild).enabled.set(new_state)
        status = "enabled" if new_state else "disabled"
        await ctx.send(f"Automatic webhook posting is now **{status}**.")

    @aw_tv_settings.command(name="status")
    async def show_status(self, ctx: commands.Context):
        """
        Show the current settings for the webhook cog.
        """
        settings = await self.config.guild(ctx.guild).all()
        source_id = settings.get("source_channel")
        dest_id = settings.get("dest_channel")
        
        source_channel = self.bot.get_channel(source_id) if source_id else "Not set"
        dest_channel = self.bot.get_channel(dest_id) if dest_id else "Not set"
        
        embed = discord.Embed(
            title="Webhook Cog Status",
            color=await ctx.embed_color()
        )
        embed.add_field(name="Status", value="Enabled" if settings.get("enabled") else "Disabled", inline=False)
        embed.add_field(name="Source Channel", value=source_channel.mention if isinstance(source_channel, discord.TextChannel) else "Not set", inline=False)
        embed.add_field(name="Destination Channel", value=dest_channel.mention if isinstance(dest_channel, discord.TextChannel) else "Not set", inline=False)
        
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot is False:
            return

        settings = await self.config.guild(message.guild).all()
        if not settings.get("enabled") or message.channel.id != settings.get("source_channel"):
            return

        dest_channel_id = settings.get("dest_channel")
        if not dest_channel_id:
            return
            
        destination_channel = self.bot.get_channel(dest_channel_id)
        if not destination_channel:
            log.warning(f"Destination channel with ID {dest_channel_id} not found.")
            return

        for embed in message.embeds:
            if embed.footer and ("Sonarr" in embed.footer.text or "Radarr" in embed.footer.text):
                new_embed = self.create_new_embed(embed)
                if new_embed:
                    try:
                        await destination_channel.send(embed=new_embed)
                    except discord.Forbidden:
                        log.error(f"Missing permissions to send message in {destination_channel.name}")
                    except Exception as e:
                        log.error(f"Failed to send embed: {e}")

    def create_new_embed(self, old_embed: discord.Embed):
        """
        Creates a new, cleaner embed from a Sonarr/Radarr webhook embed.
        """
        title = old_embed.title
        description = old_embed.description
        
        new_embed = discord.Embed(
            title=title,
            description=description,
            color=old_embed.color
        )
        
        if old_embed.thumbnail:
            new_embed.set_thumbnail(url=old_embed.thumbnail.url)
            
        return new_embed

async def setup(bot):
    await bot.add_cog(AWTV(bot))
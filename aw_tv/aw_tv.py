import discord
from redbot.core import commands, Config, checks
import logging

log = logging.getLogger("red.afterwork.tv")

class AfterWorkTV(commands.Cog, name="AfterWorkTV"):
	"""
	Sonarr/Radarr Webhook handler for Afterwork.
	"""
	def __init__(self, bot):
		self.bot = bot
		self.config = Config.get_conf(self, identifier=123456789, force_registration=True)
		self.config.register_guild(
			source_channel=None,
			dest_channel=None,
			enabled=True
		)

	@commands.group(name="tv")
	@checks.admin_or_permissions(manage_guild=True)
	async def tv_settings(self, ctx: commands.Context):
		"""
		Settings for the Sonarr/Radarr webhook cog.
		"""
		pass

	@tv_settings.command(name="channel")
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

	@tv_settings.command(name="toggle")
	async def toggle_posting(self, ctx: commands.Context):
		"""
		Enable or disable automatic posting of formatted embeds.
		"""
		current_state = await self.config.guild(ctx.guild).enabled()
		new_state = not current_state
		await self.config.guild(ctx.guild).enabled.set(new_state)
		status = "enabled" if new_state else "disabled"
		await ctx.send(f"Automatic webhook posting is now **{status}**.")

	@tv_settings.command(name="status")
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
			# This is a basic check for Sonarr/Radarr embeds which often have a footer.
			if embed.footer and ("Sonarr" in embed.footer.text or "Radarr" in embed.footer.text):
				new_embed = self.create_new_embed(embed)
				if new_embed:
					try:
						await destination_channel.send(embed=new_embed)
					except discord.Forbidden:
						log.error(f"Missing permissions to send message in {destination_channel.name}")
					except Exception as e:
						log.error(f"Failed to send embed: {e}")

	def create_new_embed(self, old_embed: discord.Embed) -> discord.Embed:
		"""
		Creates a new, formatted embed from a Sonarr/Radarr webhook embed.
		"""
		new_embed = discord.Embed(
			title="New in Library",
			color=old_embed.color
		)
        
		# Copy description and image from the original embed
		new_embed.description = old_embed.description
		if old_embed.image:
			new_embed.set_image(url=old_embed.image.url)
		elif old_embed.thumbnail:
			 new_embed.set_image(url=old_embed.thumbnail.url)

		# Add a footer to credit the source
		if old_embed.footer:
			new_embed.set_footer(text=f"via {old_embed.footer.text}")
            
		return new_embed

async def setup(bot):
	aw_tv_cog = AfterWorkTV(bot)
	await bot.add_cog(aw_tv_cog)

	await bot.wait_until_ready()
    
	primary_cog = bot.get_cog("AfterWorkBase")
	if primary_cog:
		base_command = primary_cog.afterworktest_base
		base_command.add_command(aw_tv_cog.tv_settings)
	else:
		log.error("Could not find the AfterWorkBase cog to attach commands.")
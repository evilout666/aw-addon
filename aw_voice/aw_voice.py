import discord
from redbot.core import commands, Config
import logging

log = logging.getLogger("red.afterwork.voice")

class AfterWorkVC(commands.Cog, name="AfterWorkVC"):
	"""
	Voice channel commands for Afterwork.
	"""
	def __init__(self, bot):
		self.bot = bot
		self.config = Config.get_conf(self, identifier=123456789, force_registration=True)
		# Register the same settings as in the main cog to access them
		self.config.register_guild(
			source_id=None,
			category_id=None,
			create_text_channels=False,
			embed_color=0x4287f5, 
			embed_description="Welcome, {user.mention}! Your new channel, {channel.name}, is ready to use.",
			room_channels={}
		)

	@commands.group(name="vc", invoke_without_command=True)
	async def vc_settings(self, ctx: commands.Context):
		"""
		Voice channel announcer settings.
		"""
		await ctx.send_help()

	@vc_settings.command(name="setsource")
	async def vc_set_source(self, ctx: commands.Context, source_channel: discord.VoiceChannel, category: discord.CategoryChannel):
		"""
		Sets the source voice channel and the category for new channels.
		"""
		await self.config.guild(ctx.guild).source_id.set(source_channel.id)
		await self.config.guild(ctx.guild).category_id.set(category.id)
		await ctx.send(f"Source voice channel set to **{source_channel.name}** and category to **{category.name}**.")

	@vc_settings.command(name="toggle")
	async def vc_toggle(self, ctx: commands.Context):
		"""
		Toggles the creation of private text channels for new voice channels.
		"""
		current_state = await self.config.guild(ctx.guild).create_text_channels()
		new_state = not current_state
		await self.config.guild(ctx.guild).create_text_channels.set(new_state)
		status = "enabled" if new_state else "disabled"
		await ctx.send(f"Private text channel creation has been **{status}**.")
    
	@vc_settings.command(name="setcolor")
	async def vc_set_color(self, ctx: commands.Context, color: str):
		"""
		Sets the embed color for the announcement message.
		"""
		try:
			color_int = int(color.replace("#", ""), 16)
			await self.config.guild(ctx.guild).embed_color.set(color_int)
			await ctx.send(f"Embed color set to `{color}`.")
		except ValueError:
			await ctx.send("Invalid color. Please use a hex code (e.g., `#00FFFF`).")
    
	@vc_settings.command(name="setdescription")
	async def vc_set_description(self, ctx: commands.Context, *, description: str):
		"""
		Sets the embed description for the announcement message.
		"""
		await self.config.guild(ctx.guild).embed_description.set(description)
		await ctx.send("Embed description updated.")

	@vc_settings.command(name="status")
	async def vc_status(self, ctx: commands.Context):
		"""
		Shows the current status of the voice channel announcer.
		"""
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

	@vc_settings.command(name="preview")
	async def vc_preview(self, ctx: commands.Context):
		"""
		Shows a preview of the welcome message.
		"""
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
	aw_vc_cog = AfterWorkVC(bot)
	await bot.add_cog(aw_vc_cog)

	# Wait until the bot is ready to ensure all cogs are loaded
	await bot.wait_until_ready()
    
	# Get the primary cog and its base command
	primary_cog = bot.get_cog("AfterWorkBase")
	if primary_cog:
		base_command = primary_cog.afterworktest_base
		base_command.add_command(aw_vc_cog.vc_settings)
	else:
		log.error("Could not find the AfterWorkBase cog to attach commands.")
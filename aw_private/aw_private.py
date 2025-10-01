import discord
from redbot.core import commands, Config
import logging

log = logging.getLogger("red.afterwork.private")

class AfterWorkPC(commands.Cog, name="AfterWorkPC"):
	"""
	Private channel commands for Afterwork.
	"""
	def __init__(self, bot):
		self.bot = bot
		self.config = Config.get_conf(self, identifier=123456789, force_registration=True)
		self.config.register_guild(private_channels={})

	@commands.group(name="pc", invoke_without_command=True)
	async def pc_settings(self, ctx: commands.Context):
		"""
		Private channel management settings.
		"""
		await ctx.send_help()
    
	@pc_settings.command(name="create")
	async def pc_create_channel(self, ctx: commands.Context, user: discord.Member, category: discord.CategoryChannel, *, name: str):
		"""
		Creates a private text channel accessible only by you and the specified user.
		"""
		try:
			overwrites = {
				ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
				ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
				user: discord.PermissionOverwrite(read_messages=True),
				ctx.author: discord.PermissionOverwrite(read_messages=True)
			}
			new_channel = await ctx.guild.create_text_channel(
				name=name, 
				category=category, 
				overwrites=overwrites
			)
			await ctx.send(f"Private channel **{new_channel.name}** created for {user.mention} in {category.name}.")
			await new_channel.send(f"Welcome, {user.mention}! This is your private channel with {ctx.author.mention}.")
		except discord.errors.Forbidden:
			await ctx.send("I don't have the necessary permissions to create channels or set permissions. Please check my role permissions.")
		except Exception as e:
			log.error(f"An unexpected error occurred while creating a private channel: {e}", exc_info=True)
			await ctx.send(f"An error occurred: {e}")

async def setup(bot):
	aw_pc_cog = AfterWorkPC(bot)
	await bot.add_cog(aw_pc_cog)

	# Wait until the bot is ready to ensure all cogs are loaded
	await bot.wait_until_ready()
    
	# Get the primary cog and its base command
	primary_cog = bot.get_cog("AfterWorkBase")
	if primary_cog:
		base_command = primary_cog.afterworktest_base
		base_command.add_command(aw_pc_cog.pc_settings)
	else:
		log.error("Could not find the AfterWorkBase cog to attach commands.")
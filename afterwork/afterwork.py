import discord
from redbot.core import commands, Config
import logging

log = logging.getLogger("red.afterwork.base")

class AfterWorkBase(commands.Cog, name="AfterWorkBase"):
	"""
	The base cog for Afterwork test commands.
	This cog owns the `afterworktest` command and provides a custom help menu.
	"""
	def __init__(self, bot):
		self.bot = bot
		self.config = Config.get_conf(self, identifier=123456789, force_registration=True)

	@commands.group(name="afterworktest", invoke_without_command=True)
	async def afterworktest_base(self, ctx: commands.Context):
		"""
		Displays a custom help menu for the Afterwork test commands.
		"""
		# Ensure all subcommands are loaded before building the embed
		await self.bot.wait_until_ready()

		embed = discord.Embed(
			title="🚀 Afterwork Test Commands",
			description=f"Here are the available command modules. Use `{ctx.prefix}afterworktest <module>` for more info.",
			color=await ctx.embed_color()
		)
		embed.set_footer(text="Afterwork Cogs")

		# Dynamically get subcommands and add them to the embed
		if self.afterworktest_base.commands:
			for cmd in sorted(self.afterworktest_base.commands, key=lambda c: c.name):
				embed.add_field(
					name=f"`{cmd.name}`",
					value=cmd.short_doc or "No description available.",
					inline=False
				)
		else:
			embed.add_field(
				name="No Modules Loaded",
				value="No command modules are currently attached. Please load the `aw_voice`, `aw_embed`, or `aw_private` cogs.",
				inline=False
			)
        
		await ctx.send(embed=embed)

async def setup(bot):
	await bot.add_cog(AfterWorkBase(bot))
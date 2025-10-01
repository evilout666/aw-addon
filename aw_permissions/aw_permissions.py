import discord
from redbot.core import commands, Config, app_commands
import logging

log = logging.getLogger("red.afterwork")

class AfterWork(commands.Cog):
	"""
	A unified cog that provides information about, and functionality for, Afterwork plugins.
	"""
	def __init__(self, bot):
		self.bot = bot
		self.config = Config.get_conf(self, identifier=123456789, force_registration=True)
		# Register your new config defaults here
		# self.config.register_guild(...)

	@commands.group()
	@commands.admin_or_permissions(manage_guild=True)
	async def afterwork_permissions(self, ctx: commands.Context):
		"""
		Manages permissions for AfterWork commands.
		"""
		pass

	@afterwork_permissions.command(name="list")
	async def afterwork_permissions_list(self, ctx: commands.Context):
		"""
		Lists the current permission rules for the server.
		"""
		perms_cog = self.bot.get_cog("Permissions")
		if not perms_cog:
			return await ctx.send("The Permissions cog is not loaded.")

		all_rules = await perms_cog.config.guild(ctx.guild).rules()
		if not all_rules:
			return await ctx.send("No permission rules have been set for this server.")

		embed = discord.Embed(
			title=f"Permissions for {ctx.guild.name}",
			color=await ctx.embed_color()
		)

		humanized_rules = {}
		for role_id, rules in all_rules.items():
			role = ctx.guild.get_role(int(role_id))
			if not role:
				continue
            
			for command, allowed in rules.items():
				if command not in humanized_rules:
					humanized_rules[command] = {"allow": [], "deny": []}
                
				if allowed:
					humanized_rules[command]["allow"].append(role.name)
				else:
					humanized_rules[command]["deny"].append(role.name)

		if not humanized_rules:
			return await ctx.send("No valid permission rules were found.")

		for command, roles in sorted(humanized_rules.items()):
			value = ""
			if roles["allow"]:
				value += "**Allow:** " + ", ".join(roles["allow"]) + "\n"
			if roles["deny"]:
				value += "**Deny:** " + ", ".join(roles["deny"])
			if value:
				embed.add_field(name=command, value=value, inline=False)

		if not embed.fields:
			return await ctx.send("No permission rules are currently set.")
            
		await ctx.send(embed=embed)

	@afterwork_permissions.command(name="role")
	async def afterwork_permissions_role(self, ctx: commands.Context, role: discord.Role):
		"""
		Lists the permission rules for a specific role.
		"""
		perms_cog = self.bot.get_cog("Permissions")
		if not perms_cog:
			return await ctx.send("The Permissions cog is not loaded.")

		all_rules = await perms_cog.config.guild(ctx.guild).rules()
		role_rules = all_rules.get(str(role.id))

		if not role_rules:
			return await ctx.send(f"No permission rules have been set for the **{role.name}** role.")

		embed = discord.Embed(
			title=f"Permissions for {role.name}",
			color=role.color if role.color.value != 0 else await ctx.embed_color()
		)

		allowed_commands = []
		denied_commands = []

		for command, allowed in sorted(role_rules.items()):
			if allowed:
				allowed_commands.append(f"`{command}`")
			else:
				denied_commands.append(f"`{command}`")

		if allowed_commands:
			embed.add_field(name="Allowed Commands", value=", ".join(allowed_commands), inline=False)
        
		if denied_commands:
			embed.add_field(name="Denied Commands", value=", ".join(denied_commands), inline=False)

		if not embed.fields:
			return await ctx.send(f"No specific command permissions found for the **{role.name}** role.")
            
		await ctx.send(embed=embed)

	# --- Listeners and Helper Functions ---
    
async def setup(bot):
	await bot.add_cog(AfterWork(bot))

if __name__ == "__main__":
	print("This is a cog for Red-DiscordBot and cannot be run directly.")
	print("To use this cog, load it into your bot with the command: [p]load workinprogress")
	print("Replace [p] with your bot's prefix.")
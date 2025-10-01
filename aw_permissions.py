import discord
from redbot.core import commands, Config, app_commands
import logging

log = logging.getLogger("red.afterwork")

class AfterWorkPermissions(commands.Cog, name="AfterWorkPermissions"):
    """
    Manages and displays permissions for AfterWork cogs.
    """
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=123456789, force_registration=True)
        self.afterwork_commands = ["awvoice", "awtv", "awprivate", "awembed"]

    @commands.group(name="awperms")
    @commands.admin_or_permissions(manage_guild=True)
    async def awperms(self, ctx: commands.Context):
        """
        Manages and displays permissions for AfterWork cogs.
        """
        pass

    @awperms.command(name="list")
    async def awperms_list(self, ctx: commands.Context):
        """
        Lists the current permission rules for AfterWork cogs.
        """
        perms_cog = self.bot.get_cog("Permissions")
        if not perms_cog:
            return await ctx.send("The Permissions cog is not loaded.")

        all_rules = await perms_cog.config.guild(ctx.guild).rules()
        if not all_rules:
            return await ctx.send("No permission rules have been set for this server.")

        embed = discord.Embed(
            title=f"AfterWork Permissions for {ctx.guild.name}",
            color=await ctx.embed_color()
        )

        humanized_rules = {}
        for role_id, rules in all_rules.items():
            role = ctx.guild.get_role(int(role_id))
            if not role:
                continue
            
            for command, allowed in rules.items():
                # Check if the command is one of the AfterWork commands
                if any(command.startswith(aw_cmd) for aw_cmd in self.afterwork_commands):
                    if command not in humanized_rules:
                        humanized_rules[command] = {"allow": [], "deny": []}
                    
                    if allowed:
                        humanized_rules[command]["allow"].append(role.name)
                    else:
                        humanized_rules[command]["deny"].append(role.name)

        if not humanized_rules:
            return await ctx.send("No permission rules were found for any AfterWork cogs.")

        for command, roles in sorted(humanized_rules.items()):
            value = ""
            if roles["allow"]:
                value += "**Allow:** " + ", ".join(roles["allow"]) + "\n"
            if roles["deny"]:
                value += "**Deny:** " + ", ".join(roles["deny"])
            if value:
                embed.add_field(name=command, value=value, inline=False)

        if not embed.fields:
            return await ctx.send("No AfterWork permission rules are currently set.")
            
        await ctx.send(embed=embed)

    @awperms.command(name="role")
    async def awperms_role(self, ctx: commands.Context, role: discord.Role):
        """
        Lists the AfterWork permission rules for a specific role.
        """
        perms_cog = self.bot.get_cog("Permissions")
        if not perms_cog:
            return await ctx.send("The Permissions cog is not loaded.")

        all_rules = await perms_cog.config.guild(ctx.guild).rules()
        if not all_rules:
            return await ctx.send("No permission rules have been set for this server.")

        role_rules = all_rules.get(str(role.id))

        if not role_rules:
            return await ctx.send(f"No permission rules have been set for the **{role.name}** role.")

        embed = discord.Embed(
            title=f"AfterWork Permissions for {role.name}",
            color=role.color if role.color.value != 0 else await ctx.embed_color()
        )

        allowed_commands = []
        denied_commands = []

        for command, allowed in sorted(role_rules.items()):
            if any(command.startswith(aw_cmd) for aw_cmd in self.afterwork_commands):
                if allowed:
                    allowed_commands.append(f"`{command}`")
                else:
                    denied_commands.append(f"`{command}`")

        if allowed_commands:
            embed.add_field(name="Allowed Commands", value=", ".join(allowed_commands), inline=False)
        
        if denied_commands:
            embed.add_field(name="Denied Commands", value=", ".join(denied_commands), inline=False)

        if not embed.fields:
            return await ctx.send(f"No specific AfterWork command permissions found for the **{role.name}** role.")
            
        await ctx.send(embed=embed)

    @awperms.command(name="denyall")
    @commands.is_owner()
    async def awperms_denyall(self, ctx: commands.Context):
        """Set default server rule to DENY for all loaded AfterWork cogs.
        This writes directly to the Permissions cog config for reliability.
        """
        perms_cog = self.bot.get_cog("Permissions")
        if not perms_cog:
            return await ctx.send("Permissions cog not loaded.")

        guild_conf = perms_cog.config.guild(ctx.guild)
        current_rules = await guild_conf.rules()
        if current_rules is None:
            current_rules = {}
        everyone_id = str(ctx.guild.default_role.id)
        role_rules = current_rules.get(everyone_id) or {}

        updated = 0
        target_cogs = ["AfterWorkVC", "AfterWorkTV", "AfterWorkPC", "AfterWorkEmbed"]
        for cog_name in target_cogs:
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for cmd in cog.walk_commands():
                qn = cmd.qualified_name
                if role_rules.get(qn) is False:
                    continue
                role_rules[qn] = False
                updated += 1
        current_rules[everyone_id] = role_rules
        await guild_conf.rules.set(current_rules)
        await ctx.send(f"Set DENY for {updated} commands for @everyone.")

    @awperms.command(name="allowall")
    @commands.is_owner()
    async def awperms_allowall(self, ctx: commands.Context):
        """Remove explicit DENY entries for AfterWork commands (undo denyall)."""
        perms_cog = self.bot.get_cog("Permissions")
        if not perms_cog:
            return await ctx.send("Permissions cog not loaded.")
        guild_conf = perms_cog.config.guild(ctx.guild)
        current_rules = await guild_conf.rules()
        if not current_rules:
            return await ctx.send("No permission rules stored.")
        everyone_id = str(ctx.guild.default_role.id)
        role_rules = current_rules.get(everyone_id)
        if not role_rules:
            return await ctx.send("No rules stored for @everyone.")
        removed = 0
        for command_name in list(role_rules.keys()):
            if any(command_name.startswith(prefix) for prefix in self.afterwork_commands) and role_rules[command_name] is False:
                role_rules.pop(command_name, None)
                removed += 1
        current_rules[everyone_id] = role_rules
        await guild_conf.rules.set(current_rules)
        await ctx.send(f"Removed {removed} DENY entries for AfterWork commands.")

    # --- Listeners and Helper Functions ---
    
async def setup(bot):
    await bot.add_cog(AfterWorkPermissions(bot))

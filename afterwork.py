# Red Bot Cog: afterwork
# Goal: Provide a base for test commands and add an owner-only automation 
# command to trigger a global cog update.
# NOTE: This version is simplified for a PUBLIC GITHUB REPOSITORY setup.

import discord
from redbot.core import commands, Config
import logging

log = logging.getLogger("red.afterwork.base")

# The REPO_PATH_INSIDE_CONTAINER variable and git logic are no longer needed
# because Red Bot's Downloader handles public GitHub URLs directly.

class Afterwork(commands.Cog, name="Afterwork"):
    """
    The base cog for Afterwork test commands and automation utilities.
    This cog owns the `afterwork` command group and the `update` command.
    """
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=123456789, force_registration=True)
        self.downloader_cog = None # Used by the update command

    @commands.group(name="afterwork", invoke_without_command=True)
    async def afterwork_base(self, ctx: commands.Context):
        """
        Displays a custom help menu for the Afterwork commands.
        """
        await self.bot.wait_until_ready()

        embed = discord.Embed(
            title="🚀 Afterwork Commands",
            description=f"Here are the available command modules. Use `{ctx.prefix}afterwork <module>` for more info.",
            color=await ctx.embed_color()
        )
        embed.set_footer(text="Afterwork Cogs")

        if self.afterwork_base.commands:
            for cmd in sorted(self.afterwork_base.commands, key=lambda c: c.name):
                embed.add_field(
                    name=f"`{cmd.name}`",
                    value=cmd.short_doc or "No description available.",
                    inline=False
                )
        else:
            embed.add_field(
                name="No Modules Loaded",
                value="No command modules are currently attached. Please load the necessary cogs.",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @afterwork_base.command(name="update")
    @commands.is_owner()
    async def afterwork_update(self, ctx: commands.Context):
        """
        Triggers Red Bot's built-in cog update and reload process.
        
        This assumes the repository is public and registered via 
        `!downloader repo add <URL>`.
        """
        status_message = await ctx.send("Starting automation sequence...")
        
        await status_message.edit(content="🔄 **Triggering Red Bot cog update/reload...**")

        self.downloader_cog = self.bot.get_cog("Downloader")

        if self.downloader_cog and hasattr(self.downloader_cog, 'cogupdate'):
            try:
                # Invoke the built-in cogupdate command programmatically.
                # Red's downloader will check the public GitHub URL for updates.
                await ctx.invoke(self.downloader_cog.cogupdate)
                
                # We expect cogupdate to send its own output, so we delete the status message 
                # to avoid clutter if successful, or leave it for diagnostic context if an error occurs.
                await status_message.delete()
            except Exception as e:
                await ctx.send(f"❌ **Automation Failed (Cog Reload):** Could not execute `cogupdate`. Error: {e}")
        else:
            await ctx.send("❌ **Automation Failed (Dependency):** The `Downloader` cog must be loaded for this command to work.")


async def setup(bot):
    await bot.add_cog(Afterwork(bot))

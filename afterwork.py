# Red Bot Cog: afterwork
# Goal: Provide a base for test commands and add an owner-only automation 
# command to pull latest files from GitHub and update cogs in Red.

import asyncio
import os
import discord
from redbot.core import commands, Config
import logging

log = logging.getLogger("red.afterwork.base")

# IMPORTANT: This path is set to the location where the Unraid directory
# /mnt/disk1/data/github/redbot is mounted INSIDE the Red Bot container.
REPO_PATH_INSIDE_CONTAINER = "/home/cogs"

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
        # Ensure all subcommands are loaded before building the embed
        await self.bot.wait_until_ready()

        embed = discord.Embed(
            title="🚀 Afterwork Commands",
            description=f"Here are the available command modules. Use `{ctx.prefix}afterwork <module>` for more info.",
            color=await ctx.embed_color()
        )
        embed.set_footer(text="Afterwork Cogs")

        # Dynamically get subcommands and add them to the embed
        if self.afterwork_base.commands:
            # Include the 'update' command in the menu
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
        Pulls latest files from GitHub and reloads installed cogs.
        
        This combines git pull (using the container path) and Red's cogupdate 
        command for one-step deployment.
        """
        status_message = await ctx.send("Starting automation sequence...")
        
        # --- 1. Perform Git Pull ---
        await status_message.edit(content="➡️ **Step 1/2: Pulling latest changes from GitHub...**")

        # Check if Git is available in the environment
        if not await self._is_git_available():
            await ctx.send("ERROR: Git command not found in this environment. Cannot pull new files.")
            return

        try:
            # Ensure we are in the correct directory before pulling
            # We use the container's path for internal shell commands
            os.chdir(REPO_PATH_INSIDE_CONTAINER)
            
            # Execute git pull
            process = await asyncio.create_subprocess_shell(
                "git pull",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            output = stdout.decode().strip()
            error = stderr.decode().strip()

            if process.returncode != 0:
                await status_message.edit(content=f"❌ **Step 1/2 Failed (Git Pull):**\n```bash\n{error or output}\n```\nCheck the container path and permissions.")
                return

            await status_message.edit(content=f"✅ **Step 1/2 Complete (Git Pull):**\n```bash\n{output}\n```")

        except FileNotFoundError:
            await ctx.send(f"❌ **Step 1/2 Failed (Path):** Directory not found: `{REPO_PATH_INSIDE_CONTAINER}`. Check your Red Bot volume mounts.")
            return
        except Exception as e:
            await ctx.send(f"❌ **Step 1/2 Failed (Unknown Error):** {e}")
            return

        # --- 2. Trigger Cog Update/Reload ---
        await status_message.edit(content="🔄 **Step 2/2: Triggering Red Bot cog reload...**")

        self.downloader_cog = self.bot.get_cog("Downloader")

        if self.downloader_cog and hasattr(self.downloader_cog, 'cogupdate'):
            try:
                # Invoke the built-in cogupdate command programmatically
                # This reloads the cogs using the new files pulled in Step 1
                await ctx.invoke(self.downloader_cog.cogupdate)
                # The cogupdate command itself sends final output, so we update the status
                await status_message.edit(content="🎉 **Automation Complete:** Files pulled and cogs reloaded!")
            except Exception as e:
                await ctx.send(f"❌ **Step 2/2 Failed (Cog Reload):** Could not execute `cogupdate`. Error: {e}")
        else:
            await ctx.send("❌ **Step 2/2 Failed (Dependency):** The `Downloader` cog must be loaded for this command to work.")

    async def _is_git_available(self):
        """Check if the git command is executable."""
        try:
            process = await asyncio.create_subprocess_shell(
                "which git",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.wait()
            return process.returncode == 0
        except FileNotFoundError:
            return False

async def setup(bot):
    await bot.add_cog(Afterwork(bot))

import discord
from redbot.core import commands
import logging
import asyncio

log = logging.getLogger("red.AfterworkManager")

class Afterwork(commands.Cog):
    """
    Central control panel to deploy all Afterwork configuration hubs simultaneously.
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="afterwork")
    @commands.is_owner()
    async def afterwork_command(self, ctx: commands.Context):
        """
        Executes the setup command for all loaded Afterwork cogs (VC, TV, Hide).
        
        This will deploy or redeploy the persistent configuration hub for each module.
        """
        
        # We need the current prefix to display command names correctly
        prefix = ctx.prefix 
        
        # Define the command names that need to be executed sequentially
        command_names = [
            'afterworkvc', 
            'afterworktv', 
            'afterworkhide'
        ]
        
        embed_color = await ctx.embed_color()
        
        embed = discord.Embed(
            title="✅ AfterWork Control Panel Deployment",
            description=f"Attempting to deploy/redeploy configuration hubs for all {len(command_names)} modules. Please check the channel for the pinned messages.",
            color=embed_color
        )
        success_count = 0
        
        # --- Execute Commands Sequentially ---
        
        for cmd_name in command_names:
            command = self.bot.get_command(cmd_name)
            
            if command is None:
                status = f"🔴 Command `{prefix}{cmd_name}` not found. Cog may be unloaded."
            else:
                try:
                    # Use ctx.invoke to execute the command logic, passing the current context.
                    await ctx.invoke(command)
                    status = f"🟢 Command `{prefix}{cmd_name}` executed successfully."
                    success_count += 1
                except Exception as e:
                    # Log and report any errors encountered during command execution
                    log.error(f"Error invoking {cmd_name}:", exc_info=True)
                    status = f"❗ Error executing: {e.__class__.__name__}"
            
            embed.add_field(name=cmd_name.upper(), value=status, inline=False)
            
            # Small delay between executing commands to ensure Discord API limits are respected
            await asyncio.sleep(1.5) 
            
        # --- Final Status Update ---
        embed.add_field(name="\u200b", value="---", inline=False) # Separator
        embed.add_field(
            name="Deployment Complete", 
            value=f"Successfully deployed **{success_count}/{len(command_names)}** hubs.", 
            inline=False
        )

        # Send the final summary embed
        await ctx.send(embed=embed)

def setup(bot):
    """The function Red uses to load the cog."""
    bot.add_cog(Afterwork(bot))

import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import os
import logging

log = logging.getLogger("red.awcogs.afterwork")

class CogManagerView(discord.ui.View):
    def __init__(self, bot: Red, cog_states: dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog_states = cog_states
        self.selected_cog = None
        self.update_components()

    def update_components(self):
        self.clear_items()
        options = []
        for cog_name, info in sorted(self.cog_states.items()):
            if cog_name == "afterwork":
                continue
            emoji = "✅" if info['loaded'] else "❌"
            options.append(discord.SelectOption(label=cog_name, description=info['description'][:95], emoji=emoji, value=cog_name))
        if options:
            select = discord.ui.Select(placeholder="Select a cog…", options=options, custom_id="cog_select")
            async def _callback(interaction: discord.Interaction):
                self.selected_cog = interaction.data['values'][0]
                await interaction.response.send_message(f"Selected `{self.selected_cog}`.", ephemeral=True)
            select.callback = _callback
            self.add_item(select)

        for label, style, cid in [
            ("Load", discord.ButtonStyle.green, "load"),
            ("Unload", discord.ButtonStyle.red, "unload"),
            ("Reload", discord.ButtonStyle.blurple, "reload"),
        ]:
            button = discord.ui.Button(label=label, style=style, custom_id=f"cog_{cid}")
            async def make_cb(interaction: discord.Interaction, action=cid):
                await self.handle_cog_action(interaction, action)
            button.callback = make_cb
            self.add_item(button)

    async def handle_cog_action(self, interaction: discord.Interaction, action: str):
        if not self.selected_cog:
            await interaction.response.send_message("Pick a cog first.", ephemeral=True)
            return
        target = self.selected_cog
        try:
            if action == "load":
                await self.bot.load_extension(target)
                self.cog_states[target]['loaded'] = True
                msg = f"Loaded `{target}`"
            elif action == "unload":
                await self.bot.unload_extension(target)
                self.cog_states[target]['loaded'] = False
                msg = f"Unloaded `{target}`"
            elif action == "reload":
                await self.bot.reload_extension(target)
                self.cog_states[target]['loaded'] = True
                msg = f"Reloaded `{target}`"
            else:
                msg = "Unknown action"
            await interaction.response.send_message(msg, ephemeral=True)
        except Exception as e:
            log.exception("Cog action failed")
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)
        self.update_components()
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

class AfterWork(commands.Cog):
    """Flat repo cog manager (development only)."""
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8675309, force_registration=True)

    def get_cog_info(self):
        repo_path = os.path.dirname(__file__)
        cog_info = {}
        for filename in os.listdir(repo_path):
            if not filename.endswith('.py'):
                continue
            name = filename[:-3]
            if name.startswith('_'):
                continue
            # Skip manager itself for list purposes
            description = "Standalone cog file" if name != 'afterwork' else "Manager panel"
            cog_info[name] = {
                'description': description,
                'loaded': name in self.bot.cogs,
            }
        return cog_info

    @commands.command()
    @commands.is_owner()
    async def afterwork(self, ctx: commands.Context):
        """Show management panel for flat cogs."""
        await ctx.defer()
        states = self.get_cog_info()
        embed = discord.Embed(title="AWCogs (Flat Mode)", description="Development-only manager.")
        for name, info in sorted(states.items()):
            status = "✅" if info['loaded'] else "❌"
            if name == 'afterwork':
                continue
            embed.add_field(name=name, value=f"{info['description']}\nStatus: {status}", inline=False)
        view = CogManagerView(self.bot, states)
        await ctx.send(embed=embed, view=view)

async def setup(bot: Red):
    await bot.add_cog(AfterWork(bot))

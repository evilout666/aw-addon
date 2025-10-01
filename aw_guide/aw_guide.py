import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import os
import json
import logging

log = logging.getLogger("red.AWCogs.AfterWork")

class CogManagerView(discord.ui.View):
    def __init__(self, bot: Red, cog_states: dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog_states = cog_states
        self.update_components()

    def update_components(self):
        self.clear_items()
        
        options = []
        for cog_name, info in self.cog_states.items():
            if cog_name == "AfterWork":
                continue
            label = f"{cog_name}"
            description = info['description']
            emoji = "✅" if info['loaded'] else "❌"
            options.append(discord.SelectOption(label=label, description=description, emoji=emoji, value=cog_name))

        select = discord.ui.Select(
            placeholder="Select a cog to manage...",
            options=options,
            custom_id="cog_select"
        )
        select.callback = self.on_select_cog
        self.add_item(select)

        load_button = discord.ui.Button(label="Load", style=discord.ButtonStyle.green, custom_id="load_cog", row=1)
        load_button.callback = self.on_load
        self.add_item(load_button)

        unload_button = discord.ui.Button(label="Unload", style=discord.ButtonStyle.red, custom_id="unload_cog", row=1)
        unload_button.callback = self.on_unload
        self.add_item(unload_button)

        reload_button = discord.ui.Button(label="Reload", style=discord.ButtonStyle.blurple, custom_id="reload_cog", row=1)
        reload_button.callback = self.on_reload
        self.add_item(reload_button)

        install_button = discord.ui.Button(label="Install", style=discord.ButtonStyle.primary, custom_id="install_cog", row=2)
        install_button.callback = self.on_install
        self.add_item(install_button)

        uninstall_button = discord.ui.Button(label="Uninstall", style=discord.ButtonStyle.secondary, custom_id="uninstall_cog", row=2)
        uninstall_button.callback = self.on_uninstall
        self.add_item(uninstall_button)

    async def on_select_cog(self, interaction: discord.Interaction):
        self.selected_cog = interaction.data['values'][0]
        await interaction.response.send_message(f"You selected `{self.selected_cog}`. Choose an action.", ephemeral=True)

    async def handle_cog_action(self, interaction: discord.Interaction, action: str):
        cog_name = getattr(self, 'selected_cog', None)
        if not cog_name:
            await interaction.response.send_message("Please select a cog first.", ephemeral=True)
            return

        try:
            if action == "load":
                await self.bot.load_extension(f"AWCogs.{cog_name}")
                msg = f"Successfully loaded `{cog_name}`."
                self.cog_states[cog_name]['loaded'] = True
            elif action == "unload":
                await self.bot.unload_extension(f"AWCogs.{cog_name}")
                msg = f"Successfully unloaded `{cog_name}`."
                self.cog_states[cog_name]['loaded'] = False
            elif action == "reload":
                await self.bot.reload_extension(f"AWCogs.{cog_name}")
                msg = f"Successfully reloaded `{cog_name}`."
                self.cog_states[cog_name]['loaded'] = True
            elif action == "install":
                downloader = self.bot.get_cog("Downloader")
                repo = await downloader.get_repo("AWCogs")
                if not repo:
                    await interaction.response.send_message("AWCogs repo not found by Downloader.", ephemeral=True)
                    return
                await downloader.install(repo, [cog_name])
                msg = f"Successfully installed `{cog_name}`."
            elif action == "uninstall":
                downloader = self.bot.get_cog("Downloader")
                repo = await downloader.get_repo("AWCogs")
                if not repo:
                    await interaction.response.send_message("AWCogs repo not found by Downloader.", ephemeral=True)
                    return
                await downloader.uninstall(repo, [cog_name])
                msg = f"Successfully uninstalled `{cog_name}`."
            
            await interaction.response.send_message(msg, ephemeral=True)
        except Exception as e:
            log.error(f"Error during cog action '{action}' for '{cog_name}': {e}")
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
        
        self.update_components()
        await interaction.message.edit(view=self)


    async def on_load(self, interaction: discord.Interaction):
        await self.handle_cog_action(interaction, "load")

    async def on_unload(self, interaction: discord.Interaction):
        await self.handle_cog_action(interaction, "unload")

    async def on_reload(self, interaction: discord.Interaction):
        await self.handle_cog_action(interaction, "reload")

    async def on_install(self, interaction: discord.Interaction):
        await self.handle_cog_action(interaction, "install")

    async def on_uninstall(self, interaction: discord.Interaction):
        await self.handle_cog_action(interaction, "uninstall")


class AfterWork(commands.Cog):
    """A cog to manage other cogs in the AWCogs repo."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8675309, force_registration=True)

    def get_cog_info(self):
        """Scans the repo to get information about all available cogs."""
        cog_info = {}
        repo_path = os.path.dirname(os.path.dirname(__file__)) # Gets parent of AfterWork dir
        
        for cog_name in os.listdir(repo_path):
            cog_path = os.path.join(repo_path, cog_name)
            info_path = os.path.join(cog_path, 'info.json')
            
            if os.path.isdir(cog_path) and os.path.exists(info_path):
                with open(info_path) as f:
                    info = json.load(f)
                
                cog_info[cog_name] = {
                    'description': info.get('short', 'No description available.'),
                    'loaded': cog_name in self.bot.cogs,
                    'installed': True # Placeholder, real check is harder
                }
        return cog_info

    @commands.command()
    @commands.is_owner()
    async def afterwork(self, ctx: commands.Context):
        """Displays a management panel for all cogs in the AWCogs repo."""
        await ctx.defer()
        cog_states = self.get_cog_info()
        
        embed = discord.Embed(
            title="⚙️ AWCogs Management Panel",
            description="Manage all cogs within the AWCogs repository.",
            color=await ctx.embed_color()
        )
        
        for name, info in sorted(cog_states.items()):
            status = "✅ Loaded" if info['loaded'] else "❌ Unloaded"
            import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import os
import json
import logging

log = logging.getLogger("red.AWCogs.aw_guide")

# A static list of the cogs we know are in this repository
# We will generate a message for each of these.
AW_COGS_LIST = ["aw_embed", "aw_permissions", "aw_private", "aw_tv", "aw_voice"]

class CogButtonView(discord.ui.View):
    """
    A view that provides Install, Load, and Unload buttons for a specific cog.
    """
    def __init__(self, bot: Red, cog_name: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog_name = cog_name
        # The custom_id for each button includes the cog_name to make it unique.
        self.add_item(discord.ui.Button(label="Install", style=discord.ButtonStyle.green, custom_id=f"install_{cog_name}"))
        self.add_item(discord.ui.Button(label="Load", style=discord.ButtonStyle.primary, custom_id=f"load_{cog_name}"))
        self.add_item(discord.ui.Button(label="Unload", style=discord.ButtonStyle.secondary, custom_id=f"unload_{cog_name}"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the server owner to interact with these buttons.
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("You do not have permission to use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Install", style=discord.ButtonStyle.green)
    async def install_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog_name = button.custom_id.split("_")[1]
        await interaction.response.defer()
        # We find the command and invoke it on behalf of the user.
        cmd = self.bot.get_command(f"repo install AWCogs {cog_name}")
        if cmd:
            await self.bot.invoke(interaction, cmd)
            await interaction.followup.send(f"Attempted to run `!repo install AWCogs {cog_name}`.", ephemeral=True)
        else:
            await interaction.followup.send("Could not find the `repo install` command.", ephemeral=True)

    @discord.ui.button(label="Load", style=discord.ButtonStyle.primary)
    async def load_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog_name = button.custom_id.split("_")[1]
        await interaction.response.defer()
        cmd = self.bot.get_command(f"load {cog_name}")
        if cmd:
            await self.bot.invoke(interaction, cmd)
            await interaction.followup.send(f"Attempted to run `!load {cog_name}`.", ephemeral=True)
        else:
            await interaction.followup.send("Could not find the `load` command.", ephemeral=True)

    @discord.ui.button(label="Unload", style=discord.ButtonStyle.secondary)
    async def unload_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog_name = button.custom_id.split("_")[1]
        await interaction.response.defer()
        cmd = self.bot.get_command(f"unload {cog_name}")
        if cmd:
            await self.bot.invoke(interaction, cmd)
            await interaction.followup.send(f"Attempted to run `!unload {cog_name}`.", ephemeral=True)
        else:
            await interaction.followup.send("Could not find the `unload` command.", ephemeral=True)


class AWGuide(commands.Cog):
    """A guide to the cogs in the AWCogs repo, with management buttons."""

    def __init__(self, bot: Red):
        self.bot = bot
        # We need to add the persistent view on cog load so buttons work after a restart.
        for cog_name in AW_COGS_LIST:
            self.bot.add_view(CogButtonView(self.bot, cog_name))

    @commands.command(name="aw_guide")
    @commands.is_owner()
    async def aw_guide_command(self, ctx: commands.Context):
        """Displays a guide for all cogs in the AWCogs repo."""
        await ctx.send("Below is a list of cogs available in this repository.")
        
        repo_path = os.path.dirname(os.path.dirname(__file__))

        for cog_name in sorted(AW_COGS_LIST):
            info_path = os.path.join(repo_path, cog_name, 'info.json')
            
            if os.path.exists(info_path):
                with open(info_path) as f:
                    info = json.load(f)
                
                description = info.get('long_description', info.get('short', 'No description available.'))
                
                embed = discord.Embed(
                    title=f"⚙️ {cog_name}",
                    description=description,
                    color=await ctx.embed_color()
                )
                
                view = CogButtonView(self.bot, cog_name)
                await ctx.send(embed=embed, view=view)
            else:
                await ctx.send(f"Could not find `info.json` for `{cog_name}`.")

async def setup(bot: Red):
    await bot.add_cog(AWGuide(bot))

            
        view = CogManagerView(self.bot, cog_states)
        await ctx.send(embed=embed, view=view)

async def setup(bot: Red):
    await bot.add_cog(AfterWork(bot))
import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime
from typing import Union

log = logging.getLogger("red.AfterworkMisc")

# --- UTILITY FUNCTIONS ---

def _get_admin_footer(obj: Union[commands.Context, discord.Interaction], status_action: str) -> str:
    """
    Helper to generate the administrative footer format.
    Handles both Context (from commands) and Interaction (from buttons/modals).
    """
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Check if the object is a Context from a text command
    if isinstance(obj, commands.Context):
        user_display_name = obj.author.display_name
    # Otherwise, assume it's an Interaction from a button/modal
    else:
        user_display_name = obj.user.display_name
    return f"e.Network | {status_action} by {user_display_name} {current_time}"

async def _send_owner_dm(bot, message: str):
    """Sends a critical error message directly to the bot owner."""
    owner = bot.get_user(bot.owner_id)
    if owner:
        try:
            embed = discord.Embed(
                title="⚠️ Afterwork Misc Error Notification",
                description=message,
                color=discord.Color.red()
            )
            await owner.send(embed=embed)
        except discord.Forbidden:
            log.error(f"Failed to DM owner ({owner.name}). Owner must enable DMs.")

async def _get_admin_roles(guild: discord.Guild):
    """Gets a list of roles with admin-level permissions."""
    return [role for role in guild.roles if role.permissions.administrator or role.permissions.manage_channels]

async def _apply_perms_to_channel(cog: commands.Cog, channel: discord.abc.GuildChannel, perm_action: callable):
    """Applies or reverts hiding/showing permissions for the single managed channel."""
    guild = channel.guild
    bot_member = guild.me
    
    admin_roles = await _get_admin_roles(guild)

    for role in admin_roles:
        if role < bot_member.top_role:
            try:
                # perm_action will be set_permissions for show or hide
                await perm_action(channel, role, view_channel=False, reason="Managed by AfterworkMisc")
            except discord.Forbidden:
                log.warning(f"Could not modify admin perms for '{channel.name}'.")

async def _update_setup_embed(cog: commands.Cog, guild: discord.Guild, embed: discord.Embed):
    """Refreshes the configuration data shown in the setup embed."""
    settings = await cog.config.guild(guild).all()
    channel_id = settings.get('managed_channel_id')
    
    is_hidden = await cog._is_managed_channel_hidden(guild)
    status_display = "🔴 Hidden" if is_hidden else "🟢 Visible"

    managed_channel = guild.get_channel(channel_id)
    channel_display = f"**{managed_channel.name}** (`{channel_id}`)" if managed_channel else "*Not configured*"
    
    embed.description = "This tool manages the visibility of a single Text or Voice Channel."
    embed.clear_fields()
    embed.add_field(name="Visibility Status", value=status_display, inline=False)
    embed.add_field(name="Managed Channel", value=channel_display, inline=False)
    
    return embed

# --- MODALS ---

class CategoryIDModal(discord.ui.Modal, title="Set Managed Category ID"):
    channel_id_input = discord.ui.TextInput(label="Channel ID", style=discord.TextStyle.short, placeholder="Paste the ID of the channel to manage.", required=True, max_length=20)

    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300); self.cog = cog; self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        input_id = self.channel_id_input.value.strip()
        try: channel_id = int(input_id)
        except ValueError: 
            return await interaction.followup.send("❌ **Error:** Input must be a valid Channel ID.", ephemeral=True)
        
        channel = interaction.guild.get_channel(channel_id)
        if not channel or channel.type == discord.ChannelType.category:
            return await interaction.followup.send(f"❌ **Error:** Could not find a Text or Voice Channel with the ID `{channel_id}`.", ephemeral=True)

        # --- REVERSION LOGIC ---
        old_channel_id = await self.cog.config.guild(interaction.guild).managed_channel_id()
        if old_channel_id and old_channel_id != channel_id:
            old_channel = interaction.guild.get_channel(old_channel_id)
            if old_channel:
                revert_action = lambda ch, role, view_channel, reason: ch.set_permissions(role, overwrite=None, reason=reason)
                await _apply_perms_to_channel(self.cog, old_channel, revert_action)
                log.info(f"Reverted permissions on old channel {old_channel.name} ({old_channel_id}).")

        # --- SAVE NEW CHANNEL ---
        await self.cog.config.guild(interaction.guild).managed_channel_id.set(channel_id)
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, "Channel updated"))
        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        initial_hidden = await self.cog._is_managed_channel_hidden(interaction.guild)
        view = SetupView(self.cog, initial_hidden=initial_hidden) 
        await interaction.followup.edit_message(embed=embed, view=view)


# --- VIEW ---

class SetupView(discord.ui.View):
    def __init__(self, cog: commands.Cog, initial_hidden: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        
        self.toggle_visibility_action.label = "Show" if initial_hidden else "Hide"
        self.toggle_visibility_action.style = discord.ButtonStyle.success if initial_hidden else discord.ButtonStyle.danger

    @discord.ui.button(label="Channel ID", style=discord.ButtonStyle.primary, custom_id="misc_set_category_button", row=0)
    async def set_category_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        await interaction.response.send_modal(CategoryIDModal(self.cog, interaction.message))

    @discord.ui.button(label="Hide / Show", style=discord.ButtonStyle.secondary, custom_id="misc_show_hide_button", row=0)
    async def toggle_visibility_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        settings = await self.cog.config.guild(interaction.guild).all()
        channel_id = settings.get('managed_channel_id')
        channel = interaction.guild.get_channel(channel_id)
        
        if not channel:
            return await interaction.followup.send("❌ **Error:** No channel is currently configured.", ephemeral=True)

        is_currently_hidden = await self.cog._is_managed_channel_hidden(interaction.guild)
        
        perm_action = None
        
        if is_currently_hidden: 
            action_verb = "shown (unhidden)"
            perm_action = lambda ch, role, view_channel, reason: ch.set_permissions(role, overwrite=None, reason=reason)
            new_button_label = "Hide"
            new_button_style = discord.ButtonStyle.danger
        else: 
            action_verb = "hidden"
            perm_action = lambda ch, role, view_channel, reason: ch.set_permissions(role, view_channel=False, reason=reason)
            new_button_label = "Show"
            new_button_style = discord.ButtonStyle.success
        
        await _apply_perms_to_channel(self.cog, channel, perm_action) 
        
        button.label = new_button_label
        button.style = new_button_style
        
        embed = interaction.message.embeds[0]
        status_msg = f"Channel was {action_verb}"
        embed.set_footer(text=_get_admin_footer(interaction, status_msg))
        
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await interaction.followup.edit_message(embed=embed, view=self)


# --- MAIN COG CLASS ---

class AfterworkMisc(commands.Cog, name="AfterworkMisc"): 
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=246813579, force_registration=True)
        self.config.register_guild(
            managed_channel_id=None,
            setup_message_id=None
        )

    async def initialize(self):
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                guild = self.bot.get_guild(guild_id)
                initial_hidden = await self._is_managed_channel_hidden(guild) if guild else False
                self.bot.add_view(SetupView(self, initial_hidden=initial_hidden), message_id=data['setup_message_id'])
    
    async def _is_managed_channel_hidden(self, guild: discord.Guild) -> bool:
        """
        Checks for an explicit 'View Channel: Deny' on any Administrator role for the single managed channel.
        """
        settings = await self.config.guild(guild).all()
        channel_id = settings.get('managed_channel_id')
        channel = guild.get_channel(channel_id)
        
        if not channel:
            return False 

        # Check overwrites only on the managed channel
        for target, overwrite in channel.overwrites.items():
            if isinstance(target, discord.Role) and target.permissions.administrator:
                if overwrite.view_channel is False: return True
                else: return False
                    
        return False

    @commands.group(name="afterworkmisc")
    @commands.is_owner()
    async def afterworkmisc(self, ctx: commands.Context):
        """The Afterwork Miscellaneous Configuration Panel."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @afterworkmisc.command(name="deploy")
    @commands.is_owner()
    async def afterworkmisc_deploy(self, ctx: commands.Context):
        bot_member = ctx.guild.me
        if not bot_member.guild_permissions.manage_roles:
            return await _send_owner_dm(self.bot, f"Setup failed in **{ctx.guild.name}**. I need the **Manage Roles** permission to modify channel visibility.")
        
        old_message_id = await self.config.guild(ctx.guild).setup_message_id()
        if old_message_id:
            try: 
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException: pass

        initial_hidden = await self._is_managed_channel_hidden(ctx.guild)

        description = (
            "This tool manages the visibility of a single channel. "
            "Hidden from roles with Administrator or Manage Channels permissions."
        )
        initial_embed = discord.Embed(title="Hidden Channel", description=description, color=discord.Color.blue())
        initial_embed = await _update_setup_embed(self, ctx.guild, initial_embed)
        
        view = SetupView(self, initial_hidden=initial_hidden) 
        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        await sent_message.pin(reason="Afterwork Misc Configuration Hub.")
        await self.config.guild(ctx.guild).setup_message_id.set(sent_message.id)
        
        await ctx.message.delete()
        await asyncio.sleep(1)
        try:
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception: pass

async def setup(bot):
    cog = AfterworkMisc(bot)
    await cog.initialize()
    await bot.add_cog(cog)

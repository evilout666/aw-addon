import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime

log = logging.getLogger("red.AfterworkHide")

# --- UTILITY FUNCTIONS ---

async def _send_owner_dm(bot, message: str):
    """Sends a critical error message directly to the bot owner."""
    owner_id = bot.owner_id
    owner = bot.get_user(owner_id)
    if owner:
        try:
            embed = discord.Embed(
                title="⚠️ Afterwork Hide Error Notification",
                description=message,
                color=discord.Color.red()
            )
            await owner.send(embed=embed)
        except discord.Forbidden:
            log.error(f"Failed to DM owner ({owner.name}). Owner must enable DMs.")

async def _get_admin_roles(guild: discord.Guild):
    """Gets a list of roles with admin-level permissions."""
    admin_roles = []
    for role in guild.roles:
        if role.permissions.administrator or role.permissions.manage_channels:
            admin_roles.append(role)
    return admin_roles

async def _apply_perms_to_category(cog: commands.Cog, guild: discord.Guild, perm_action: callable):
    """Applies or reverts hiding/showing permissions across all channels in the managed category.
    This function only targets Admin/Manager roles for denial/reversion."""
    bot_member = guild.me
    settings = await cog.config.guild(guild).all()
    category_id = settings.get('managed_category_id')
    
    if not category_id:
        await _send_owner_dm(cog.bot, f"Permission update failed in **{guild.name}**. Category ID is not configured.")
        return

    category = guild.get_channel(category_id)
    if not isinstance(category, discord.CategoryChannel):
        await _send_owner_dm(cog.bot, f"Permission update failed in **{guild.name}**. Configured ID `{category_id}` is not a category.")
        return

    admin_roles = await _get_admin_roles(guild)

    # Iterate through all channels in the category
    channels_to_manage = [
        c for c in category.channels if isinstance(c, (discord.TextChannel, discord.VoiceChannel))
    ]

    for channel in channels_to_manage:
        # Action: Deny View Channel for Admin Roles
        for role in admin_roles:
            if role < bot_member.top_role:
                try:
                    # perm_action is a lambda defined in SetupView
                    await perm_action(channel, role, view_channel=False, reason="Managed by AfterworkHide")
                except discord.Forbidden:
                    log.warning(f"Could not modify admin perms for '{channel.name}'.")


async def _update_setup_embed(cog: commands.Cog, guild: discord.Guild, embed: discord.Embed):
    """Refreshes the configuration data shown in the setup embed."""
    settings = await cog.config.guild(guild).all()
    category_id = settings.get('managed_category_id')
    is_enabled = settings.get('enabled', False)
    
    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    
    # Category Status
    category_channel = guild.get_channel(category_id)
    category_display = f"**{category_channel.name}** (`{category_id}`)" if category_channel else "*Not configured*"
    
    # Channel list preview (shows channels in the managed category)
    channel_list_str = "*None*"
    if category_channel and isinstance(category_channel, discord.CategoryChannel):
        channels = [c.mention for c in category_channel.channels if isinstance(c, (discord.TextChannel, discord.VoiceChannel))]
        channel_list_str = "\n".join(channels) if channels else "*Empty Category*"

    embed.clear_fields()
    embed.add_field(name="System Status", value=status_emoji, inline=False)
    embed.add_field(name="Managed Category", value=category_display, inline=False)
    embed.add_field(name="Channels in Category", value=channel_list_str, inline=False)
    
    return embed

# --- MODALS ---

class CategoryIDModal(discord.ui.Modal, title="Set Managed Category ID"):
    category_id_input = discord.ui.TextInput(label="Category ID", style=discord.TextStyle.short, placeholder="Paste the ID of the channel category to manage.", required=True, max_length=20)

    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300); self.cog = cog; self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        input_id = self.category_id_input.value.strip()
        try: category_id = int(input_id)
        except ValueError: 
            # ERROR: Send publicly
            return await interaction.followup.send("❌ **Error:** Input must be a valid Category ID.")
        
        category = interaction.guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            # ERROR: Send publicly
            return await interaction.followup.send(f"❌ **Error:** Could not find a Category Channel with the ID `{category_id}`.")

        await self.cog.config.guild(interaction.guild).managed_category_id.set(category_id)
        
        # SUCCESS: Send ephemeral (private)
        await interaction.followup.send(f"✅ Managed Category set to **{category.name}**.", ephemeral=True)
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=f"Category updated by {interaction.user.display_name}")
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await self.original_message.edit(embed=embed)


# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    @discord.ui.button(label="Category ID", style=discord.ButtonStyle.primary, custom_id="hide_set_category_button", row=0)
    async def set_category_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): 
            # ERROR: Send publicly
            return await interaction.response.send_message("Only owner can use this.", ephemeral=False) 
        await interaction.response.send_modal(CategoryIDModal(self.cog, interaction.message))

    @discord.ui.button(label="Hide / Show", style=discord.ButtonStyle.primary, custom_id="hide_show_button", row=0)
    async def hide_show_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): 
            # ERROR: Send publicly
            return await interaction.response.send_message("Only owner can use this.", ephemeral=False)
        
        await interaction.response.defer(thinking=True)
        
        settings = await self.cog.config.guild(interaction.guild).all()
        category_id = settings.get('managed_category_id')
        category = interaction.guild.get_channel(category_id)
        
        if not category or not isinstance(category, discord.CategoryChannel) or not category.channels:
            # ERROR: Send publicly
            return await interaction.followup.send("❌ **Error:** No category is configured or the category is empty.")

        is_currently_enabled = settings.get('enabled')
        
        perm_action = None
        if is_currently_enabled: 
            action_verb = "shown (unhidden)"
            perm_action = lambda ch, role, view_channel, reason: ch.set_permissions(
                role, overwrite=None, reason=reason
            )
        else: 
            action_verb = "hidden"
            perm_action = lambda ch, role, view_channel, reason: ch.set_permissions(
                role, view_channel=False, reason=reason
            )
        
        await _apply_perms_to_category(self.cog, interaction.guild, perm_action)
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=f"Channels were {action_verb} by {interaction.user.display_name}")
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await interaction.message.edit(embed=embed, view=self)
        
        # SUCCESS: Send ephemeral (private)
        await interaction.followup.send(f"Managed channels have been **{action_verb}** for admins.", ephemeral=True)


    @discord.ui.button(label="Enable/Disable", style=discord.ButtonStyle.secondary, custom_id="hide_toggle_button", row=0)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): 
            # ERROR: Send publicly
            return await interaction.response.send_message("Only owner can use this.", ephemeral=False)
        
        await interaction.response.defer(thinking=True)
        new_state = not (await self.cog.config.guild(interaction.guild).enabled())
        await self.cog.config.guild(interaction.guild).enabled.set(new_state)
        
        perm_action = None
        
        if new_state: # Enabling/Hiding (Deny for Admins)
             perm_action = lambda ch, role, view_channel, reason: ch.set_permissions(
                role, view_channel=False, reason=reason
            )
        else: # Disabling/Showing (Revert Admin Denial)
            perm_action = lambda ch, role, view_channel, reason: ch.set_permissions(
                role, overwrite=None, reason=reason
            )

        await _apply_perms_to_category(self.cog, interaction.guild, perm_action)
        
        button.label = "Disable" if new_state else "Enable"
        button.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success
        
        embed = interaction.message.embeds[0]
        embed.set_footer(text=f"System status toggled by {interaction.user.display_name}")
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await interaction.message.edit(embed=embed, view=self)
        
        # SUCCESS: Send ephemeral (private)
        await interaction.followup.send(f"System has been **{'enabled' if new_state else 'disabled'}** and permissions were updated.", ephemeral=True)

# --- MAIN COG CLASS ---

class AfterworkHide(commands.Cog, name="AfterworkHide"):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=246813579, force_registration=True)
        self.config.register_guild(
            enabled=False,
            managed_category_id=None,
            setup_message_id=None
        )

    async def initialize(self):
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                self.bot.add_view(SetupView(self, initial_enabled=data.get('enabled', False)), message_id=data['setup_message_id'])

    @commands.command(name="afterworkhide")
    @commands.is_owner()
    async def afterworkhide_command(self, ctx: commands.Context):
        bot_member = ctx.guild.me
        if not bot_member.guild_permissions.manage_roles:
            return await _send_owner_dm(self.bot, f"Setup failed in **{ctx.guild.name}**. I need the **Manage Roles** permission to modify channel visibility.")
        
        old_message_id = await self.config.guild(ctx.guild).setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException: pass

        initial_embed = discord.Embed(title="Hidden Channel", color=discord.Color.dark_theme())
        initial_embed = await _update_setup_embed(self, ctx.guild, initial_embed)
        initial_enabled = await self.config.guild(ctx.guild).enabled()
        
        view = SetupView(self, initial_enabled=initial_enabled)
        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        await sent_message.pin(reason="Afterwork Hide Configuration Hub.")
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
    cog = AfterworkHide(bot)
    await cog.initialize()
    await bot.add_cog(cog)

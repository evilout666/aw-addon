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

async def _apply_hiding_perms(cog: commands.Cog, guild: discord.Guild, channel: discord.TextChannel):
    """Hides a channel from admin roles and makes it visible to allowed roles."""
    bot_member = guild.me
    admin_roles = await _get_admin_roles(guild)
    allowed_role_ids = await cog.config.guild(guild).allowed_roles()

    # Hide from admins
    for role in admin_roles:
        if role < bot_member.top_role:
            try:
                await channel.set_permissions(role, view_channel=False, reason="Channel hidden by AfterworkHide")
            except discord.Forbidden:
                log.warning(f"Could not hide channel from role '{role.name}' due to permissions.")

    # Show to allowed roles
    for role_id in allowed_role_ids:
        role = guild.get_role(role_id)
        if role and role < bot_member.top_role:
            try:
                await channel.set_permissions(role, view_channel=True, reason="Channel access granted by AfterworkHide")
            except discord.Forbidden:
                log.warning(f"Could not grant access to role '{role.name}' due to permissions.")

async def _revert_hiding_perms(cog: commands.Cog, guild: discord.Guild, channel: discord.TextChannel):
    """Restores default visibility of a channel."""
    bot_member = guild.me
    admin_roles = await _get_admin_roles(guild)
    allowed_role_ids = await cog.config.guild(guild).allowed_roles()

    # Revert admin perms
    for role in admin_roles:
         if role < bot_member.top_role:
            try:
                await channel.set_permissions(role, overwrite=None, reason="Channel unhidden by AfterworkHide")
            except discord.Forbidden:
                log.warning(f"Could not unhide channel for role '{role.name}' due to permissions.")
    
    # Revert allowed role perms
    for role_id in allowed_role_ids:
        role = guild.get_role(role_id)
        if role and role < bot_member.top_role:
            try:
                await channel.set_permissions(role, overwrite=None, reason="Channel access reverted by AfterworkHide")
            except discord.Forbidden:
                log.warning(f"Could not revert access for role '{role.name}' due to permissions.")


async def _update_setup_embed(cog: commands.Cog, guild: discord.Guild, embed: discord.Embed):
    """Refreshes the configuration data shown in the setup embed."""
    settings = await cog.config.guild(guild).all()
    hidden_channel_ids = settings.get('hidden_channels', [])
    allowed_role_ids = settings.get('allowed_roles', [])
    is_enabled = settings.get('enabled', False)
    
    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    
    # Format hidden channels list
    channel_list_str = "\n".join(
        f"- {guild.get_channel(ch_id).mention} (`{ch_id}`)" if guild.get_channel(ch_id) else f"- *Unknown Channel* (`{ch_id}`)"
        for ch_id in hidden_channel_ids
    ) or "*None*"

    # Format allowed roles list
    role_list_str = "\n".join(
        f"- {guild.get_role(r_id).mention} (`{r_id}`)" if guild.get_role(r_id) else f"- *Unknown Role* (`{r_id}`)"
        for r_id in allowed_role_ids
    ) or "*None*"


    embed.clear_fields()
    embed.add_field(name="System Status", value=status_emoji, inline=False)
    embed.add_field(name="Managed Hidden Channels", value=channel_list_str, inline=False)
    embed.add_field(name="Allowed Roles", value=role_list_str, inline=False)
    
    return embed

# --- MODALS ---

class ChannelIDModal(discord.ui.Modal, title="Add or Remove a Hidden Channel"):
    channel_id_input = discord.ui.TextInput(label="Channel ID", style=discord.TextStyle.short, placeholder="Paste the ID of the channel to hide or unhide.", required=True, max_length=20)

    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300); self.cog = cog; self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        input_id = self.channel_id_input.value.strip()
        try: channel_id = int(input_id)
        except ValueError: return await interaction.followup.send("❌ **Error:** Input must be a valid channel ID.")
        
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send(f"❌ **Error:** Could not find a Text Channel with the ID `{channel_id}`.")

        async with self.cog.config.guild(interaction.guild).hidden_channels() as hidden_channels:
            if channel_id in hidden_channels:
                hidden_channels.remove(channel_id)
                await _revert_hiding_perms(self.cog, interaction.guild, channel)
                action = "unhidden"
            else:
                hidden_channels.append(channel_id)
                if await self.cog.config.guild(interaction.guild).enabled():
                    await _apply_hiding_perms(self.cog, interaction.guild, channel)
                action = "hidden"
        
        await interaction.followup.send(f"✅ Channel {channel.mention} has been **{action}**.")
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=f"Channel list updated by {interaction.user.display_name}")
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await self.original_message.edit(embed=embed)

class RoleIDModal(discord.ui.Modal, title="Add or Remove an Allowed Role"):
    role_id_input = discord.ui.TextInput(label="Role ID", style=discord.TextStyle.short, placeholder="Paste the ID of the role to allow or disallow.", required=True, max_length=20)

    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300); self.cog = cog; self.original_message = original_message
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        input_id = self.role_id_input.value.strip()
        try: role_id = int(input_id)
        except ValueError: return await interaction.followup.send("❌ **Error:** Input must be a valid role ID.")

        role = interaction.guild.get_role(role_id)
        if not role: return await interaction.followup.send(f"❌ **Error:** Could not find a Role with the ID `{role_id}`.")

        async with self.cog.config.guild(interaction.guild).allowed_roles() as allowed_roles:
            if role_id in allowed_roles:
                allowed_roles.remove(role_id)
                action = "removed from"
            else:
                allowed_roles.append(role_id)
                action = "added to"
        
        # Apply permission changes immediately to all hidden channels
        hidden_channel_ids = await self.cog.config.guild(interaction.guild).hidden_channels()
        if await self.cog.config.guild(interaction.guild).enabled():
            for channel_id in hidden_channel_ids:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    await _apply_hiding_perms(self.cog, interaction.guild, channel)

        await interaction.followup.send(f"✅ Role {role.mention} has been **{action}** the allowed list.")

        embed = self.original_message.embeds[0]
        embed.set_footer(text=f"Allowed roles updated by {interaction.user.display_name}")
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await self.original_message.edit(embed=embed)


# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    @discord.ui.button(label="Add/Remove Channel", style=discord.ButtonStyle.primary, custom_id="hide_add_remove_channel_button")
    async def add_remove_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        await interaction.response.send_modal(ChannelIDModal(self.cog, interaction.message))

    @discord.ui.button(label="Manage Allowed Roles", style=discord.ButtonStyle.primary, custom_id="hide_manage_roles_button")
    async def manage_roles_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        await interaction.response.send_modal(RoleIDModal(self.cog, interaction.message))

    @discord.ui.button(label="Enable/Disable", style=discord.ButtonStyle.secondary, custom_id="hide_toggle_button")
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        
        await interaction.response.defer(thinking=True)
        new_state = not (await self.cog.config.guild(interaction.guild).enabled())
        await self.cog.config.guild(interaction.guild).enabled.set(new_state)
        
        hidden_channel_ids = await self.cog.config.guild(interaction.guild).hidden_channels()
        perm_action = _apply_hiding_perms if new_state else _revert_hiding_perms
        
        for channel_id in hidden_channel_ids:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                await perm_action(self.cog, interaction.guild, channel)
        
        button.label = "Disable" if new_state else "Enable"
        button.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success
        
        embed = interaction.message.embeds[0]
        embed.set_footer(text=f"System status toggled by {interaction.user.display_name}")
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send(f"System has been **{'enabled' if new_state else 'disabled'}**.", ephemeral=True)

# --- MAIN COG CLASS ---

class AfterworkHide(commands.Cog, name="AfterworkHide"):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=246813579, force_registration=True)
        self.config.register_guild(
            enabled=False,
            hidden_channels=[],
            allowed_roles=[],
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


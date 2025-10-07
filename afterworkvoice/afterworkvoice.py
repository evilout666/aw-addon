import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime

log = logging.getLogger("red.AfterworkVoice")

# --- UTILITY FUNCTIONS ---

def _get_admin_footer(interaction: discord.Interaction, status_action: str) -> str:
    """Helper to generate the administrative footer format."""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return f"e.Network | {status_action} by {interaction.user.display_name} {current_time}"

async def _send_owner_dm(bot, message: str):
    """Sends a critical error message directly to the bot owner."""
    owner_id = bot.owner_id
    owner = bot.get_user(owner_id)
    if owner:
        try:
            embed = discord.Embed(
                title="⚠️ Afterwork Voice Error Notification",
                description=message,
                color=discord.Color.red()
            )
            await owner.send(embed=embed)
        except discord.Forbidden:
            log.error(f"Failed to DM owner ({owner.name}). Owner must enable DMs.")

async def _update_setup_embed(cog: commands.Cog, guild: discord.Guild, embed: discord.Embed):
    """Refreshes the configuration data shown in the setup embed."""
    settings = await cog.config.guild(guild).all()
    source_id = settings.get('source_id')
    is_enabled = settings.get('enabled', False)

    source_channel = cog.bot.get_channel(source_id)
    
    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    source_name = f"**{source_channel.name}** (`{source_id}`)" if source_channel else "*Not configured*"
    
    embed.description = "Use this panel to set the source voice channel where new rooms are spawned."
    embed.clear_fields()
    
    embed.add_field(name="System Status", value=status_emoji, inline=False)
    embed.add_field(name="Source VC (Join Channel)", value=source_name, inline=False)
    
    return embed

# --- MODALS ---

class ChannelIDModal(discord.ui.Modal, title="Set Source Voice Channel"):
    channel_id_input = discord.ui.TextInput(
        label="Voice Channel ID (Numbers Only)",
        style=discord.TextStyle.short,
        placeholder="Paste the ID of the VC you want to use as the source.",
        required=True,
        max_length=20,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        input_id = self.channel_id_input.value.strip()
        
        try:
            channel_id = int(input_id)
        except ValueError:
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. User: {interaction.user.display_name}. Configuration failed: Invalid Channel ID input (`{input_id}`).")
            return await interaction.response.defer()
        
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. User: {interaction.user.display_name}. Configuration failed: ID `{channel_id}` is not a valid Voice Channel.")
            return await interaction.response.defer()
        
        await self.cog.config.guild(interaction.guild).source_id.set(channel_id)
        await self.cog.config.guild(interaction.guild).enabled.set(True)
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, "Source ID updated"))

        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        view = SetupView(self.cog, initial_enabled=True)
        # Success is acknowledged by the embed update, no ephemeral message needed.
        await interaction.response.edit_message(embed=embed, view=view)

# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    @discord.ui.button(label="Channel ID", style=discord.ButtonStyle.primary, custom_id="voice_set_button", row=0)
    async def set_source_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Unauthorized access: User {interaction.user.display_name} attempted to use owner controls.")
            return await interaction.response.defer()

        modal = ChannelIDModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Enable/Disable", style=discord.ButtonStyle.secondary, custom_id="voice_toggle_button", row=0)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Unauthorized access: User {interaction.user.display_name} attempted to use owner controls.")
            return await interaction.response.defer()
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        new_state = not (await self.cog.config.guild(interaction.guild).enabled())
        await self.cog.config.guild(interaction.guild).enabled.set(new_state)
        
        button.label = "Disable" if new_state else "Enable"
        button.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success
        
        embed = interaction.message.embeds[0]
        status_msg = f"System {'enabled' if new_state else 'disabled'}"
        embed.set_footer(text=_get_admin_footer(interaction, status_msg))
        
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await interaction.message.edit(embed=embed, view=self)
        
        # Success is acknowledged by the embed update, no ephemeral message needed.
        await interaction.followup.defer()

# --- VOICE CHANNEL CONTROLS (Room Owner View) ---

class VoiceChannelButtons(discord.ui.View):
    def __init__(self, cog: commands.Cog, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=None)
        self.cog = cog
        self.voice_channel = voice_channel
        self.selected_member_id = None
        self.member_select = discord.ui.Select(placeholder="Select a member to manage...", custom_id="voice_member_select", options=[discord.SelectOption(label="Refreshing...", value="none")])
        self.kick_button = discord.ui.Button(label="Kick", style=discord.ButtonStyle.danger, custom_id="voice_kick", disabled=True)
        self.transfer_button = discord.ui.Button(label="Transfer", style=discord.ButtonStyle.blurple, custom_id="voice_transfer", disabled=True)
        self.refresh_button = discord.ui.Button(label="Refresh", style=discord.ButtonStyle.secondary, custom_id="voice_refresh")
        self.privacy_button = discord.ui.Button(label="Make Private", style=discord.ButtonStyle.secondary, custom_id="voice_privacy_toggle")
        self.add_item(self.member_select)
        self.add_item(self.kick_button)
        self.add_item(self.transfer_button)
        self.add_item(self.refresh_button)
        self.add_item(self.privacy_button)
        self.member_select.callback = self.on_member_select
        self.kick_button.callback = self.on_kick
        self.transfer_button.callback = self.on_transfer
        self.refresh_button.callback = self.on_refresh
        self.privacy_button.callback = self.on_privacy_toggle
        
    @classmethod
    async def create(cls, cog: commands.Cog, voice_channel: discord.VoiceChannel):
        view = cls(cog, voice_channel)
        await view._update_member_options()
        return view

    async def _update_member_options(self):
        vc = self.cog.bot.get_channel(self.voice_channel.id)
        if not vc:
            self.member_select.options = [discord.SelectOption(label="Channel not found", value="none")]
            return
        async with self.cog.config.guild(vc.guild).room_channels() as rooms:
            owner_id = rooms.get(str(vc.id), {}).get("owner_id")
        options = [discord.SelectOption(label=member.display_name, value=str(member.id)) for member in vc.members if member.id != owner_id]
        if not options:
            self.member_select.options = [discord.SelectOption(label="No other members in channel", value="none")]
            self.member_select.disabled = True
        else:
            self.member_select.options = options
            self.member_select.disabled = False

    async def _check_owner(self, interaction: discord.Interaction) -> bool:
        if not self.voice_channel:
             await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Error: Could not determine target voice channel during interaction check.")
             await interaction.response.defer()
             return False
        async with self.cog.config.guild(interaction.guild).room_channels() as room_channels:
            room_data = room_channels.get(str(self.voice_channel.id))
            if not room_data or room_data.get("owner_id") != interaction.user.id:
                await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Room: {self.voice_channel.name}. User: {interaction.user.display_name} is not the room owner and tried to use controls.")
                await interaction.response.defer()
                return False
        return True

    async def on_member_select(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction): return
        selection = interaction.data.get("values")
        if not selection or selection[0] == "none":
            self.selected_member_id = None
            self.kick_button.disabled = True
            self.transfer_button.disabled = True
            self.member_select.placeholder = "Select a member to manage..."
        else:
            self.selected_member_id = int(selection[0])
            member = interaction.guild.get_member(self.selected_member_id)
            self.member_select.placeholder = f"Selected: {member.display_name}" if member else "Select a member to manage..."
            self.kick_button.disabled = False
            self.transfer_button.disabled = False
        await interaction.response.edit_message(view=self)

    async def on_kick(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction) or not self.selected_member_id:
            return
        member_to_kick = interaction.guild.get_member(self.selected_member_id)
        if not member_to_kick:
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Room: {self.voice_channel.name}. Error: Member with ID {self.selected_member_id} not found during kick attempt.")
            return await interaction.response.defer()
            
        try:
            await member_to_kick.move_to(None, reason=f"Kicked by room owner {interaction.user.name}")
            # Success: Member is kicked. Acknowledge silently.
            await interaction.response.defer()
        except discord.Forbidden:
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Room: {self.voice_channel.name}. Error: Bot lacks permission to kick {member_to_kick.display_name}.")
            return await interaction.response.defer()
        
        await self._update_member_options()
        self.kick_button.disabled = True
        self.transfer_button.disabled = True
        self.selected_member_id = None
        await interaction.message.edit(view=self)

    async def on_transfer(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction) or not self.selected_member_id:
            return
        new_owner = interaction.guild.get_member(self.selected_member_id)
        if not new_owner:
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Room: {self.voice_channel.name}. Error: New owner with ID {self.selected_member_id} not found during transfer attempt.")
            return await interaction.response.defer()
            
        async with self.cog.config.guild(interaction.guild).room_channels() as room_channels:
            room_data = room_channels.get(str(self.voice_channel.id))
            if not room_data:
                await interaction.response.defer()
                return
            room_data["owner_id"] = new_owner.id
            
        original_embed = interaction.message.embeds[0]
        original_embed.set_field_at(0, name="Current Owner", value=new_owner.mention, inline=False)
        
        # Success: Ownership transferred. Acknowledge silently.
        await interaction.response.defer()
        
        await self._update_member_options()
        self.kick_button.disabled = True
        self.transfer_button.disabled = True
        self.selected_member_id = None
        await interaction.message.edit(embed=original_embed, view=self)
        
    async def on_refresh(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction): return
        # Success: List refreshed. Acknowledge silently.
        await interaction.response.defer()
        await self._update_member_options()
        await interaction.message.edit(view=self)

    async def on_privacy_toggle(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction): return
        overwrites = self.voice_channel.overwrites_for(interaction.guild.default_role)
        is_public = overwrites.connect is not False
        try:
            if is_public:
                overwrites.connect = False
                await self.voice_channel.set_permissions(interaction.guild.default_role, overwrite=overwrites)
                for member in self.voice_channel.members:
                    await self.voice_channel.set_permissions(member, connect=True)
                self.privacy_button.label = "Make Public"
                self.privacy_button.style = discord.ButtonStyle.success
            else:
                overwrites.connect = None
                await self.voice_channel.set_permissions(interaction.guild.default_role, overwrite=overwrites)
                self.privacy_button.label = "Make Private"
                self.privacy_button.style = discord.ButtonStyle.secondary
            
            # Success: Privacy toggled. Acknowledge silently.
            await interaction.response.edit_message(view=self)
        except discord.Forbidden:
            await _send_owner_dm(self.cog.bot, f"Guild: {interaction.guild.name}. Room: {self.voice_channel.name}. Error: Bot lacks permission to change channel privacy.")
            return await interaction.response.defer()

# --- MAIN COG CLASS ---

class AfterworkVoice(commands.Cog, name="AfterworkVoice"):
    """Provides voice channel control panels for temporary rooms created by an external cog."""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=123456789, force_registration=True)
        self.config.register_guild(
            enabled=False,
            source_id=None,
            setup_message_id=None,
            room_channels={}
        )

    async def initialize(self):
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                guild = self.bot.get_guild(guild_id)
                if guild: 
                    initial_enabled = data.get('enabled', False)
                    self.bot.add_view(SetupView(self, initial_enabled=initial_enabled), message_id=data['setup_message_id'])
                else:
                    log.warning(f"Skipping view initialization for missing guild ID: {guild_id}")

    @commands.group(name="afterworkvoice")
    @commands.is_owner()
    async def afterworkvoice_group(self, ctx: commands.Context):
        """Management commands for the AfterworkVoice cog."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @afterworkvoice_group.command(name="deploy")
    async def afterworkvoice_deploy(self, ctx: commands.Context):
        """Deploys the persistent configuration hub for Afterwork Voice."""
        bot_member = ctx.guild.get_member(self.bot.user.id)
        perms = ctx.channel.permissions_for(bot_member)
        if not perms.send_messages or not perms.manage_messages:
            return await _send_owner_dm(self.bot, f"Config failed in **{ctx.guild.name}**. Need Send/Manage Messages in **#{ctx.channel.name}**.")

        old_message_id = await self.config.guild(ctx.guild).setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException: pass

        initial_embed = discord.Embed(title="Voice Channel Control", color=discord.Color.blue())
        initial_embed = await _update_setup_embed(self, ctx.guild, initial_embed)
        initial_enabled = await self.config.guild(ctx.guild).enabled()
        
        view = SetupView(self, initial_enabled=initial_enabled)
        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        await sent_message.pin(reason="Afterwork Voice Configuration Hub.")
        await self.config.guild(ctx.guild).setup_message_id.set(sent_message.id)
        
        await ctx.message.delete()
        await asyncio.sleep(1)
        try:
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception: pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        config = await self.config.guild(guild).all()

        if not config.get("enabled"): return
        source_id = config.get("source_id")

        if after.channel and after.channel.id == source_id:
            try:
                def check(m, b, a):
                    return (
                        m.id == member.id
                        and b.channel and b.channel.id == source_id
                        and a.channel is not None
                        and a.channel.id != source_id
                    )
                
                _, _, moved_to_state = await self.bot.wait_for(
                    "voice_state_update", check=check, timeout=15.0
                )
                new_voice_channel = moved_to_state.channel
                
                async with self.cog.config.guild(guild).room_channels() as room_channels:
                    room_channels[str(new_voice_channel.id)] = {"owner_id": member.id}

                embed = discord.Embed(
                    title="Voice Channel Controls",
                    description=f"You are the owner of **{new_voice_channel.name}**.",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Current Owner", value=member.mention, inline=False)
                embed.add_field(name="Controls", value="Use buttons to manage members and privacy.", inline=False)
                
                embed.set_footer(text="e.Network | Available Right Now on Jellyfin")
                
                view = await VoiceChannelButtons.create(self, new_voice_channel)
                # Send the initial control panel message.
                await new_voice_channel.send(content=member.mention, embed=embed, view=view)

            except asyncio.TimeoutError:
                message = (
                    f"User **{member.display_name}** joined the Source VC but was not moved within 15 seconds. "
                    "This usually means the external AutoRoom cog failed to create the channel."
                )
                log.warning(message)
                await _send_owner_dm(self.bot, f"Guild: {guild.name} (ID: {guild.id})\n{message}")

async def setup(bot):
    cog = AfterworkVoice(bot)
    await cog.initialize()
    await bot.add_cog(cog)

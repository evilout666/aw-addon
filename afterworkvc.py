import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime

log = logging.getLogger("red.AfterWorkVC")

# --- UTILITY FUNCTIONS ---

async def _send_owner_dm(bot, message: str):
    """Sends a critical error message directly to the bot owner."""
    owner_id = bot.owner_id
    owner = bot.get_user(owner_id)
    if owner:
        try:
            embed = discord.Embed(
                title="⚠️ Afterwork VC Error Notification",
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
    source_channel = cog.bot.get_channel(source_id)
    is_enabled = settings.get('enabled', False)
    
    # Logic for System Status display
    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    source_name = f"**{source_channel.name}** (`{source_id}`)" if source_channel else "*Not yet configured*"
    
    # Update embed description/fields
    embed.description = (
        "Use this panel to verify the system status and update the Source Voice Channel ID.\n\n"
        "**Instructions:** Copy the desired Voice Channel ID, then click the button below to paste it."
    )
    
    embed.clear_fields()
    
    # Field 1: System Status
    embed.add_field(name="System Status", value=status_emoji, inline=True)
    
    # Field 2: Source VC Target
    embed.add_field(name="Source VC (Join Channel)", value=source_name, inline=False)
    
    return embed

# --- MODAL (The Fill-in Box for ID Input) ---

class ChannelIDModal(discord.ui.Modal, title="Set Source Voice Channel"):
    """
    A Modal that pops up to collect the Channel ID from the user.
    """
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
            return await interaction.response.send_message(
                "❌ **Error:** Input must be a valid channel ID (numbers only).", 
                ephemeral=True
            )
        
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            return await interaction.response.send_message(
                f"❌ **Error:** Could not find a Voice Channel with the ID `{channel_id}`.", 
                ephemeral=True
            )
        
        # --- Save configuration: Set ID and ensure system is enabled ---
        await self.cog.config.guild(interaction.guild).source_id.set(channel_id)
        await self.cog.config.guild(interaction.guild).enabled.set(True) # Force enable on new configuration
        
        # Update the original setup message to reflect the change
        embed = self.original_message.embeds[0]
        
        # Update Footer with accountability info
        embed.set_footer(text=f"Last updated by {interaction.user.display_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        # Edit message to update the embed and dynamically update the button state
        view = SetupView(self.cog, initial_enabled=True)
        await interaction.response.edit_message(embed=embed, view=view)

# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    """
    A persistent view containing the button that launches the Modal and the Toggle Button.
    """
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        
        # Dynamically set the initial state of the toggle button (Activation Button)
        self.toggle_system.label = "Deactivate System" if initial_enabled else "Activate System"
        # Green for Activate/Success, Red for Deactivate/Danger
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    @discord.ui.button(label="Set/Override Channel ID", style=discord.ButtonStyle.primary, custom_id="vc_set_button", row=0)
    async def set_source_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button callback that sends the ChannelIDModal to the user."""
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only the bot owner can use this setup tool.", ephemeral=True)

        modal = ChannelIDModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Toggle System State", style=discord.ButtonStyle.secondary, custom_id="vc_toggle_button", row=0)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggles the 'enabled' state of the listener."""
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only the bot owner can use this toggle.", ephemeral=True)
        
        new_state = not (await self.cog.config.guild(interaction.guild).enabled())
        await self.cog.config.guild(interaction.guild).enabled.set(new_state)
        
        # Update button appearance and label
        button.label = "Deactivate System" if new_state else "Activate System"
        # Green for Activate/Success, Red for Deactivate/Danger
        button.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success

        # Update the embed status field
        embed = interaction.message.embeds[0]
        embed.set_footer(text=f"Status toggled by {interaction.user.display_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        await _update_setup_embed(self.cog, interaction.guild, embed)

        await interaction.response.edit_message(embed=embed, view=self)


# --- VOICE CHANNEL CONTROLS (Room Owner View) ---
# NOTE: VoiceChannelButtons class remains unchanged from the previous version.

class VoiceChannelButtons(discord.ui.View):
    """
    A persistent view containing controls for the temporary voice channel,
    such as kicking members, transferring ownership, and toggling privacy.
    """
    def __init__(self, cog: commands.Cog, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=None)
        self.cog = cog
        self.voice_channel = voice_channel
        self.selected_member_id = None

        self.member_select = discord.ui.Select(placeholder="Select a member to manage...", custom_id="member_select", options=[discord.SelectOption(label="Refreshing...", value="none")])
        self.kick_button = discord.ui.Button(label="Kick", style=discord.ButtonStyle.danger, custom_id="kick", disabled=True)
        self.transfer_button = discord.ui.Button(label="Transfer", style=discord.ButtonStyle.blurple, custom_id="transfer", disabled=True)
        self.refresh_button = discord.ui.Button(label="Refresh", style=discord.ButtonStyle.secondary, custom_id="refresh")
        self.privacy_button = discord.ui.Button(label="Make Private", style=discord.ButtonStyle.secondary, custom_id="privacy_toggle")

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
             await interaction.response.send_message("Error: Could not determine the target voice channel.", ephemeral=True)
             return False
        async with self.cog.config.guild(interaction.guild).room_channels() as room_channels:
            room_data = room_channels.get(str(self.voice_channel.id))
            if not room_data or room_data.get("owner_id") != interaction.user.id:
                await interaction.response.send_message("You are not the room owner.", ephemeral=True)
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
            await interaction.response.defer()
            return
        member_to_kick = interaction.guild.get_member(self.selected_member_id)
        if not member_to_kick:
            await interaction.response.defer()
            return
        try:
            await member_to_kick.move_to(None, reason=f"Kicked by room owner {interaction.user.name}")
            await interaction.response.defer()
        except discord.Forbidden:
            await interaction.response.defer()
        await self._update_member_options()
        self.kick_button.disabled = True
        self.transfer_button.disabled = True
        self.selected_member_id = None
        await interaction.message.edit(view=self)

    async def on_transfer(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction) or not self.selected_member_id:
            await interaction.response.defer()
            return
        new_owner = interaction.guild.get_member(self.selected_member_id)
        if not new_owner:
            await interaction.response.defer()
            return
        async with self.cog.config.guild(interaction.guild).room_channels() as room_channels:
            room_data = room_channels.get(str(self.voice_channel.id))
            if not room_data:
                await interaction.response.defer()
                return
            room_data["owner_id"] = new_owner.id
        original_embed = interaction.message.embeds[0]
        original_embed.set_field_at(0, name="Current Owner", value=new_owner.mention, inline=False)
        await interaction.message.edit(embed=original_embed)
        await interaction.response.defer()
        await self._update_member_options()
        self.kick_button.disabled = True
        self.transfer_button.disabled = True
        self.selected_member_id = None
        await interaction.message.edit(view=self)
        
    async def on_refresh(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction): return
        await self._update_member_options()
        await interaction.response.edit_message(view=self)

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
            await interaction.response.edit_message(view=self)
        except discord.Forbidden:
            await interaction.response.defer()
            log.error(f"Missing permissions to change privacy settings for {self.voice_channel.name}")


# --- MAIN COG CLASS ---

class AfterWorkVC(commands.Cog, name="AfterWorkVC"):
    """
    Provides voice channel control panels for temporary rooms created by an external cog.
    Configuration is handled via a persistent interactive hub message, restricted to the bot owner.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=123456789, force_registration=True)
        
        self.config.register_guild(
            enabled=False, # System starts disabled until configured/enabled
            source_id=None,
            setup_message_id=None, # For storing the ID of the persistent hub message
            room_channels={} # {voice_channel_id: {"owner_id": id}}
        )

    async def initialize(self):
        """Asynchronous initialization method."""
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                # We need to pass the initial state for the button to load correctly
                initial_enabled = data.get('enabled', False)
                self.bot.add_view(SetupView(self, initial_enabled=initial_enabled), message_id=data['setup_message_id'])

    def cog_unload(self):
        log.info("AfterWorkVC unloaded.")
        
    # --- SINGLE COMMAND: [p]afterworkvc ---

    @commands.command(name="afterworkvc")
    @commands.is_owner() # Restricted to bot owner
    async def afterworkvc_command(self, ctx: commands.Context):
        """
        Posts the permanent interactive configuration hub for Afterwork Voice Control.
        
        Run this command once in your dedicated settings channel. The message will be pinned.
        """
        # --- 0. Permission Pre-check ---
        bot_member = ctx.guild.get_member(self.bot.user.id)
        perms = ctx.channel.permissions_for(bot_member)
        if not perms.send_messages or not perms.manage_messages:
            await _send_owner_dm(self.bot, 
                f"Configuration failed in **{ctx.guild.name}** (`{ctx.guild.id}`). "
                f"I need **Send Messages** and **Manage Messages** permissions in channel **#{ctx.channel.name}** to post and pin the hub."
            )
            return # Exit silently if permissions are missing (error handled via DM)
        
        # --- 1. Cleanup Old Hub ---
        settings = await self.config.guild(ctx.guild).all()
        old_message_id = settings.get('setup_message_id')
        
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.NotFound:
                log.warning(f"Old setup message ID {old_message_id} found in config but message not found in channel. Proceeding with new post.")
            except discord.HTTPException:
                log.error(f"Failed to delete old setup message {old_message_id}. Ignoring.")


        # --- 2. Post New Hub ---
        initial_embed = discord.Embed(
            title="Voice Channel", # Final title as requested
            color=discord.Color.blue()
        )
        
        # Populate initial status and description
        initial_embed = await _update_setup_embed(self, ctx.guild, initial_embed)
        
        # Initialize view with current enabled state
        initial_enabled = await self.config.guild(ctx.guild).enabled()
        view = SetupView(self, initial_enabled=initial_enabled)

        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        # --- 3. Pin and Store ID ---
        await sent_message.pin(reason="Afterwork VC Configuration Hub.")
        await self.config.guild(ctx.guild).setup_message_id.set(sent_message.id)
        
        # --- 4. Clean up Command Invocation and Pin Notification ---
        await ctx.message.delete()
        
        # Delete the automatic "X pinned a message" system message
        await asyncio.sleep(1) 
        try:
            # Fetch the channel history for the latest system message (the pin notification)
            async for message in ctx.channel.history(limit=5):
                # The pin system message has type PINS_ADD, and the author is the bot itself (for its own pin)
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception:
            # We already checked manage_messages, so any failure here is logged but ignored for core functionality
            pass


    # --- LISTENERS (Core Functionality) ---
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        config = await self.config.guild(guild).all()

        # Check if the system is globally disabled
        if not config.get("enabled"):
            return

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
                
                # Wait for the external AutoRoom cog to move the user
                _, _, moved_to_state = await self.bot.wait_for(
                    "voice_state_update", check=check, timeout=15.0
                )
                new_voice_channel = moved_to_state.channel
                
                async with self.config.guild(guild).room_channels() as room_channels:
                    room_channels[str(new_voice_channel.id)] = {"owner_id": member.id}

                embed = discord.Embed(
                    title="Voice Channel Controls",
                    description=f"You are the owner of **{new_voice_channel.name}**.",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Current Owner", value=member.mention, inline=False)
                embed.add_field(name="Controls", value="Use buttons to manage members and privacy.", inline=False)
                
                view = await VoiceChannelButtons.create(self, new_voice_channel)
                # Post the control panel in the newly created VC
                await new_voice_channel.send(content=member.mention, embed=embed, view=view)

            except asyncio.TimeoutError:
                message = (
                    f"User **{member.display_name}** joined the Source VC but was not moved within 15 seconds. "
                    "This usually means the external AutoRoom cog failed to create the channel."
                )
                log.warning(message)
                await _send_owner_dm(self.bot, f"Guild: {guild.name} (ID: {guild.id})\n{message}")


# --- RED SETUP FUNCTION ---

async def setup(bot):
    """The function Red uses to load the cog."""
    cog = AfterWorkVC(bot)
    # The setup view must be added asynchronously via initialize() to ensure persistence on restart
    await cog.initialize()
    await bot.add_cog(cog)

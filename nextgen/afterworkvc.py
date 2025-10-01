import discord
from redbot.core import commands, Config
import logging
import asyncio

# The name of the logger should match the cog name/file for clarity
log = logging.getLogger("red.AfterWorkVC")

# --- VIEWS (Keep the View class outside the Cog for cleaner structure) ---

class VoiceChannelButtons(discord.ui.View):
    # NOTE: For true persistence on bot restart, you would need to store the 
    # message IDs of the control panel and retrieve them here.
    # The current setup assumes the message is live during the session.

    def __init__(self, cog: commands.Cog, voice_channel: discord.VoiceChannel = None):
        # We need to pass the voice_channel when the view is created dynamically,
        # but for bot.add_view() on startup, we must be able to call it without args.
        # Since this view is dynamically created, we'll keep the channel arg here.
        super().__init__(timeout=None)
        self.cog = cog
        self.voice_channel = voice_channel
        self.selected_member_id = None

        # Define components in init
        self.member_select = discord.ui.Select(
            placeholder="Select a member to manage...",
            custom_id="member_select",
            options=[discord.SelectOption(label="Refreshing...", value="none")]
        )
        self.kick_button = discord.ui.Button(label="Kick", style=discord.ButtonStyle.danger, custom_id="kick", disabled=True)
        self.transfer_button = discord.ui.Button(label="Transfer", style=discord.ButtonStyle.blurple, custom_id="transfer", disabled=True)
        self.refresh_button = discord.ui.Button(label="Refresh", style=discord.ButtonStyle.secondary, custom_id="refresh")
        self.privacy_button = discord.ui.Button(label="Make Private", style=discord.ButtonStyle.secondary, custom_id="privacy_toggle")

        # Add items to the view
        self.add_item(self.member_select)
        self.add_item(self.kick_button)
        self.add_item(self.transfer_button)
        self.add_item(self.refresh_button)
        self.add_item(self.privacy_button)

        # Set callbacks (must be done this way as they are defined as methods)
        self.member_select.callback = self.on_member_select
        self.kick_button.callback = self.on_kick
        self.transfer_button.callback = self.on_transfer
        self.refresh_button.callback = self.on_refresh
        self.privacy_button.callback = self.on_privacy_toggle
        
    # --- Class Method for Dynamic Creation ---
    @classmethod
    async def create(cls, cog: commands.Cog, voice_channel: discord.VoiceChannel):
        """Asynchronously create and initialize the view."""
        view = cls(cog, voice_channel)
        await view._update_member_options()
        return view

    # --- Utility methods (kept as is) ---
    async def _update_member_options(self):
        vc = self.cog.bot.get_channel(self.voice_channel.id) # Use the channel passed on creation
        # ... rest of your original _update_member_options logic ...
        if not vc:
            self.member_select.options = [discord.SelectOption(label="Channel not found", value="none")]
            return

        async with self.cog.config.guild(vc.guild).room_channels() as rooms:
            owner_id = rooms.get(str(vc.id), {}).get("owner_id")
        
        options = [
            discord.SelectOption(label=member.display_name, value=str(member.id))
            for member in vc.members if member.id != owner_id
        ]

        if not options:
            self.member_select.options = [discord.SelectOption(label="No other members in channel", value="none")]
            self.member_select.disabled = True
        else:
            self.member_select.options = options
            self.member_select.disabled = False

    async def _check_owner(self, interaction: discord.Interaction) -> bool:
        """Checks if the interacting user is the owner of the voice channel.
           Also ensures self.voice_channel is correctly set, using interaction.channel if available.
        """
        if self.voice_channel is None and interaction.channel is not None:
             # In case of persistence reload, the channel might be missing, 
             # but the view is likely attached to a text channel (where the command is sent)
             # or a message in a text channel that links to the VC.
             # You might need to adjust this logic if the VC is not the interaction channel.
             # Assuming the control panel is in a TEXT channel related to the VC.
             # For a persistent view, the VC needs to be derived from the interaction's channel name/parent, 
             # or stored in the config.
             pass # Sticking to the original logic for now, as dynamic view creation is safer.

        async with self.cog.config.guild(interaction.guild).room_channels() as room_channels:
            # IMPORTANT: For persistent views, you must find the VC ID.
            # Since this view is created dynamically, we'll assume self.voice_channel is correct.
            vc_id = self.voice_channel.id 
            room_data = room_channels.get(str(vc_id))
            if not room_data or room_data.get("owner_id") != interaction.user.id:
                await interaction.response.defer()
                return False
        return True

    # --- Callbacks (kept as is, but ensure they use self.voice_channel) ---
    async def on_member_select(self, interaction: discord.Interaction):
        # ... original logic ...
        if not await self._check_owner(interaction):
            return
        
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
        # ... original logic ...
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
        # ... original logic ...
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
            
            # The channel where the control panel message is located is the interaction channel.
            # Your original code was attempting to use the voice channel as the text channel:
            # text_channel = self.voice_channel 
            # This needs to be the message's text channel if you want to set its permissions.
            # Since the user only has one VC and no corresponding TEXT channel in their config, 
            # I will remove the text channel permission logic to avoid confusion/errors.
            # You may need to re-add it if you configure a corresponding text channel in the main Afterwork cog.

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
        if not await self._check_owner(interaction):
            return
            
        await self._update_member_options()
        await interaction.response.edit_message(view=self)

    async def on_privacy_toggle(self, interaction: discord.Interaction):
        # ... original logic ...
        if not await self._check_owner(interaction):
            return

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
                overwrites.connect = True
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
    Voice channel commands for Afterwork, handling room management controls.
    NOTE: This cog relies on another 'AutoRoom' cog to create the channels.
    """
    
    # Placeholder for persistent views
    # self.persisted_view = VoiceChannelButtons(self)

    def __init__(self, bot):
        self.bot = bot
        # Identifier is typically a unique random number.
        self.config = Config.get_conf(self, identifier=123456789, force_registration=True)
        
        self.config.register_guild(
            enabled=False,
            source_id=None,
            category_id=None,
            room_channels={} # {voice_channel_id: {"owner_id": id}}
        )

    # --- New: Asynchronous setup for modern Red cogs ---
    async def initialize(self):
        """Asynchronous initialization method."""
        # This is where you would load persisted views if you were storing message IDs.
        # Example of re-adding a persistent view (requires a message ID to be stored):
        # await self.bot.add_view(VoiceChannelButtons(self))
        pass

    # --- New: Unload hook (good practice for cleanup) ---
    def cog_unload(self):
        """Clean up when the cog is unloaded."""
        # This is where you would stop loops or remove views if they were added globally.
        log.info("AfterWorkVC unloaded.")
        
    # --- Commands (kept as is) ---

    @commands.group(name="awvoice", invoke_without_command=True)
    # ... rest of your commands (voice_settings, setsource, status, enable, disable) ...
    async def voice_settings(self, ctx: commands.Context):
        """Voice channel announcer settings."""
        await ctx.send_help()

    @voice_settings.command(name="setsource")
    @commands.admin_or_permissions(manage_channels=True)
    async def voice_set_source(self, ctx: commands.Context, source_channel: discord.VoiceChannel, category: discord.CategoryChannel):
        """Sets the source voice channel and the category for new channels."""
        await self.config.guild(ctx.guild).source_id.set(source_channel.id)
        await self.config.guild(ctx.guild).category_id.set(category.id)
        await ctx.send(f"Source voice channel set to **{source_channel.name}** and category to **{category.name}**.")

    @voice_settings.command(name="status")
    async def voice_status(self, ctx: commands.Context):
        """Shows the current status of the voice channel announcer."""
        settings = await self.config.guild(ctx.guild).all()
        source_channel = self.bot.get_channel(settings['source_id']) if settings['source_id'] else None
        category = self.bot.get_channel(settings['category_id']) if settings['category_id'] else None
        source_name = source_channel.mention if source_channel else "Not set"
        category_name = category.mention if category else "Not set"
        enabled_status = "Enabled" if settings.get("enabled") else "Disabled"
        embed = discord.Embed(
            title="Voice Channel Announcer Status",
            description="Here's the current configuration for the voice channel announcements.",
            color=await ctx.embed_color()
        )
        embed.add_field(name="Status", value=enabled_status, inline=False)
        embed.add_field(name="Source Channel", value=source_name, inline=False)
        embed.add_field(name="Channel Category", value=category_name, inline=False)
        await ctx.send(embed=embed)

    @voice_settings.command(name="enable")
    @commands.admin_or_permissions(manage_guild=True)
    async def voice_enable(self, ctx: commands.Context):
        """Enables the auto-room text channel creation."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("Auto-room text channel creation is now **enabled**.")

    @voice_settings.command(name="disable")
    @commands.admin_or_permissions(manage_guild=True)
    async def voice_disable(self, ctx: commands.Context):
        """Disables the auto-room text channel creation."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("Auto-room text channel creation is now **disabled**.")


    # --- Listeners (kept as is) ---
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        Handles the logic for posting the control panel when a user
        joins a voice channel created by the AutoRoom cog.
        """
        guild = member.guild
        config = await self.config.guild(guild).all()

        if not config.get("enabled"):
            return

        source_id = config.get("source_id")

        # Scenario 1: User joins the source channel to create a new room.
        if after.channel and after.channel.id == source_id:
            try:
                # Wait for the AutoRoom cog to move the user to a new channel.
                # NOTE: The name 'AutoRoom' suggests an external cog is doing the moving.
                def check(m, b, a):
                    return (
                        m.id == member.id
                        and b.channel and b.channel.id == source_id
                        and a.channel is not None
                        and a.channel.id != source_id
                    )
                
                _, _, moved_to_state = await self.bot.wait_for(
                    "voice_state_update", check=check, timeout=10.0
                )
                new_voice_channel = moved_to_state.channel
                
                # Store the relationship
                async with self.config.guild(guild).room_channels() as room_channels:
                    room_channels[str(new_voice_channel.id)] = {"owner_id": member.id}

                # Prepare and send the welcome message with buttons.
                embed = discord.Embed(
                    title="Voice Channel Controls",
                    description=(
                        f"These are the controls for the channel, **{new_voice_channel.name}**."
                    ),
                    color=discord.Color.blue()
                )
                embed.add_field(name="Current Owner", value=member.mention, inline=False)
                embed.add_field(
                    name="Controls",
                    value=(
                        "• **Dropdown Menu**: Select a user in the channel to manage.\n"
                        "• **Kick**: Kicks the selected user from the voice channel.\n"
                        "• **Transfer**: Transfers ownership of this channel to the selected user.\n"
                        "• **Refresh**: Updates the list of members in the dropdown.\n"
                        "• **Make Public/Private**: Toggles whether anyone can join the voice channel."
                    ),
                    inline=False
                )
                
                # Create the dynamic view instance
                view = await VoiceChannelButtons.create(self, new_voice_channel)
                await new_voice_channel.send(content=member.mention, embed=embed, view=view)

            except asyncio.TimeoutError:
                log.warning(f"User {member.name} joined the source channel but was not moved.")

        # Scenario 2: User leaves a voice channel, which might be a temporary room.
        # Original logic removed channel deletion, which is correct since another cog handles creation/deletion.
        pass


# --- New: Asynchronous setup function ---

async def setup(bot):
    """The function Red uses to load the cog."""
    cog = AfterWorkVC(bot)
    # Call the asynchronous initialization method
    await cog.initialize()
    await bot.add_cog(cog)

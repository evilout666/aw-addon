import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime

log = logging.getLogger("red.AfterWorkVC")

# --- UTILITY FUNCTION: Send Error DM to Owner ---

async def _send_owner_dm(bot: commands.Bot, guild: discord.Guild, error_message: str, error_type: str = "Error"):
    """Sends a detailed DM to the bot owner regarding a critical guild-specific error."""
    owner_id = (await bot.get_application_info()).owner.id
    owner = bot.get_user(owner_id)
    if owner:
        dm_content = (
            f"❌ **{error_type} in AfterWorkVC Cog**\n\n"
            f"**Guild:** {guild.name} (`{guild.id}`)\n"
            f"**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"**Details:** {error_message}"
        )
        try:
            await owner.send(dm_content)
        except Exception:
            log.exception(f"Failed to send owner DM for error in {guild.name}.")
    else:
        log.error(f"Owner not found to send error DM for {guild.type}: {error_message}")


# --- UTILITY FUNCTION: Update Config Embed ---

async def _update_setup_embed(cog: commands.Cog, guild: discord.Guild, embed: discord.Embed):
    """Refreshes the configuration data shown in the setup embed."""
    settings = await cog.config.guild(guild).all()
    source_id = settings.get('source_id')
    source_channel = cog.bot.get_channel(source_id)
    
    # Logic: System is considered Active if a source ID is present and the channel is found.
    status_is_active = source_id is not None and source_channel is not None
    status_emoji = "🟢 Active" if status_is_active else "🔴 Inactive"
    
    source_name = f"**{source_channel.name}** (`{source_id}`)" if source_channel else "*Not yet configured*"
    
    embed.clear_fields()
    embed.description = (
        "Use this panel to verify the system status and update the Source Voice Channel ID.\n\n"
        "**Instructions:** Copy the desired Voice Channel ID, then click the button below to paste it."
    )
    
    embed.add_field(name="System Status", value=status_emoji, inline=True)
    embed.add_field(name="Source VC (Join Channel)", value=source_name, inline=False)
    
    return embed

# --- MODAL (The Fill-in Box) ---

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
        
        # --- Save configuration ---
        await self.cog.config.guild(interaction.guild).source_id.set(channel_id)
        
        # Update the original setup message to reflect the change
        embed = self.original_message.embeds[0]
        embed.set_footer(text=f"Last updated by {interaction.user.display_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        # Edit the message to show success (suppresses the ephemeral follow-up)
        await interaction.response.edit_message(embed=embed)


# --- VIEW (The Persistent Setup Button) ---

class SetupView(discord.ui.View):
    """
    A persistent view containing the button that launches the Modal.
    """
    def __init__(self, cog: commands.Cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Set/Override Channel ID", style=discord.ButtonStyle.primary, custom_id="vc_set_button")
    async def set_source_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Button callback that sends the ChannelIDModal to the user.
        """
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only the bot owner can use this setup tool.", ephemeral=True)

        modal = ChannelIDModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

# --- VOICE CHANNEL CONTROLS (Room Owner View) ---

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
            enabled=True,
            source_id=None,
            room_channels={}, # {voice_channel_id: {"owner_id": id}}
            setup_message_id=None, # Stored ID for the configuration hub message
        )

    async def initialize(self):
        """Asynchronous initialization method."""
        pass

    def cog_unload(self):
        log.info("AfterWorkVC unloaded.")
        
    # --- SINGLE COMMAND: [p]afterworkvc ---

    @commands.command(name="afterworkvc")
    @commands.is_owner()
    async def afterworkvc_command(self, ctx: commands.Context):
        """
        Posts the permanent interactive configuration hub for Afterwork Voice Control.
        
        Run this command once in your dedicated settings channel. The message will be pinned.
        """
        bot_perms = ctx.channel.permissions_for(ctx.guild.me)
        
        if not bot_perms.send_messages or not bot_perms.manage_messages:
            # DM owner if required permissions are missing
            await _send_owner_dm(
                ctx.bot, ctx.guild,
                f"I need both 'Send Messages' and 'Manage Messages' permissions "
                f"in channel #{ctx.channel.name} (`{ctx.channel.id}`) to manage the setup hub.",
                error_type="Missing Permissions"
            )
            return

        settings = await self.config.guild(ctx.guild).all()
        old_message_id = settings.get("setup_message_id")

        # --- Cleanup: Check for and delete old setup hub message ---
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
                log.info(f"Deleted old setup message (ID: {old_message_id}) in {ctx.guild.name}.")
            except discord.NotFound:
                log.info(f"Old setup message (ID: {old_message_id}) not found, proceeding with new post.")
            except discord.Forbidden:
                log.error(f"Forbidden to delete old setup hub in {ctx.channel.name}.")
            finally:
                await self.config.guild(ctx.guild).setup_message_id.set(None)
        
        # --- Post New Hub ---
        initial_embed = discord.Embed(
            title="Voice Channel",
            color=discord.Color.blue()
        )
        
        initial_embed = await _update_setup_embed(self, ctx.guild, initial_embed)
        
        try:
            sent_message = await ctx.send(embed=initial_embed, view=SetupView(self))
            await sent_message.pin(reason="Afterwork VC Configuration Hub for owner access.")
            
            await self.config.guild(ctx.guild).setup_message_id.set(sent_message.id)
            await ctx.message.delete()
            
        except discord.Forbidden as e:
            await _send_owner_dm(
                ctx.bot, ctx.guild,
                f"Failed to post or pin the hub in #{ctx.channel.name}. Details: {e}",
                error_type="Setup Failure"
            )

    # --- LISTENERS (Core Functionality) ---
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        config = await self.config.guild(guild).all()

        if not config.get("source_id"):
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
                await new_voice_channel.send(content=member.mention, embed=embed, view=view)

            except asyncio.TimeoutError:
                await _send_owner_dm(
                    member.bot, guild,
                    f"User {member.display_name} joined the source VC but was **not moved** by the external cog (Timeout: 15s). "
                    "The voice control panel was not posted.",
                    error_type="External Cog Failure"
                )
            except Exception as e:
                await _send_owner_dm(
                    member.bot, guild,
                    f"Unexpected error creating control panel for {member.display_name}: {e}",
                    error_type="Runtime Error"
                )

        pass


# --- RED SETUP FUNCTION ---

async def setup(bot):
    """The function Red uses to load the cog."""
    cog = AfterWorkVC(bot)
    await cog.initialize()
    await bot.add_cog(cog)

import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime
import json
from typing import Optional

log = logging.getLogger("red.AfterworkMB") 

# --- UTILITY FUNCTIONS ---

def _get_admin_footer(obj, status_action: str) -> str:
    """Helper to generate the administrative footer format."""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if isinstance(obj, commands.Context):
        user_display_name = obj.author.display_name
    else:
        user_display_name = obj.user.display_name
        
    return f"e.Network | {status_action} by {user_display_name} {current_time}"

async def _send_owner_dm(bot, message: str):
    """Sends a critical error message directly to the bot owner."""
    owner_id = bot.owner_id
    owner = bot.get_user(owner_id)
    if owner:
        try:
            embed = discord.Embed(
                title="⚠️ Afterwork MB Error Notification",
                description=message,
                color=discord.Color.red()
            )
            await owner.send(embed=embed)
        except discord.Forbidden:
            log.error(f"Failed to DM owner ({owner.name}). Owner must enable DMs.")

async def _update_setup_embed(cog: commands.Cog, guild: discord.Guild, embed: discord.Embed):
    """Refreshes the configuration data shown in the setup embed."""
    settings = await cog.config.guild(guild).all()
    named_channels = settings.get('named_channels', {})
    is_enabled = settings.get('enabled', False)

    # List all saved named channels
    channel_list = []
    if named_channels:
        for name, id in named_channels.items():
            channel = guild.get_channel(id)
            channel_name = f"#{channel.name}" if channel else "Unknown Channel"
            channel_list.append(f"• **{name}** -> {channel_name} (`{id}`)")
        channel_list_display = "\n".join(channel_list)
    else:
        channel_list_display = "*No named channels configured*"
    
    # CHANGE APPLIED: Removed "Click Message..." sentence
    embed.description = (
        "Configure and save channel IDs with a name, then use that name to send the embed message."
    )
    
    embed.clear_fields()
    
    # CHANGE APPLIED: Only add fields if the system is ENABLED
    if is_enabled:
        embed.add_field(name="Configured Channels (Name -> ID)", value=channel_list_display, inline=False)
        
        embed.add_field(
            name="Message Payload", 
            value="Use an Online Editor to generate the message JSON: [afterwork.evilout666.com/embed_builder](http://afterwork.evilout666.com/embed_builder).", 
            inline=False
        )
    
    return embed

# --- MODALS (omitted for brevity, assume unchanged) ---

class NamedChannelSetModal(discord.ui.Modal, title="Save Named Channel ID"):
    name_input = discord.ui.TextInput(
        label="Configuration Name (e.g., 'general')",
        style=discord.TextStyle.short,
        placeholder="A unique name to reference this channel.",
        required=True,
        max_length=50,
    )
    channel_id_input = discord.ui.TextInput(
        label="Source Channel ID (Numbers Only)",
        style=discord.TextStyle.short,
        placeholder="ID where messages will be sent.",
        required=True,
        max_length=20,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        name = self.name_input.value.strip().lower()
        input_channel_id = self.channel_id_input.value.strip()
        
        try:
            channel_id = int(input_channel_id)
        except ValueError:
            return await interaction.followup.send("❌ **Error:** Channel ID must be a valid number.", ephemeral=True)
            
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send(f"❌ **Error:** Could not find a Text Channel with the ID `{channel_id}`.", ephemeral=True)

        # Save to named_channels
        async with self.cog.config.guild(interaction.guild).named_channels() as channels:
            channels[name] = channel_id
        
        # Update the original setup message
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"Channel '{name}' updated"))

        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        view = SetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).enabled())
        await self.original_message.edit(embed=embed, view=view)
        
        await interaction.followup.send(f"✅ Channel **{name}** set to **#{channel.name}**.", ephemeral=True)


class NamedMessageSendModal(discord.ui.Modal, title="Send Embed Message"):
    name_input = discord.ui.TextInput(
        label="Configuration Name",
        style=discord.TextStyle.short,
        placeholder="The name of the saved channel (e.g., 'general').",
        required=True,
        max_length=50,
    )
    json_input = discord.ui.TextInput(
        label="JSON Embed Payload",
        style=discord.TextStyle.long,
        placeholder='{"title": "Title", "description": "Text"}',
        required=True,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        name = self.name_input.value.strip().lower()
        json_payload = self.json_input.value.strip()
        
        settings = await self.cog.config.guild(interaction.guild).all()
        named_channels = settings.get('named_channels', {})
        
        # 1. Channel Lookup
        channel_id = named_channels.get(name)
        if not channel_id:
            return await interaction.followup.send(f"❌ **Error:** No channel found with the name `{name}`. Use the 'Channel ID' button to save one.", ephemeral=True)
        
        target_channel = interaction.guild.get_channel(channel_id)
        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            return await interaction.followup.send(f"❌ **Error:** Saved Channel for `{name}` is invalid or not a text channel.", ephemeral=True)
            
        # 2. Save new JSON payload and Validate
        try:
            embed_data = json.loads(json_payload)
            if not isinstance(embed_data, dict):
                raise ValueError("JSON must be an object.")
            await self.cog.config.guild(interaction.guild).json_payload.set(json_payload) 
        except (json.JSONDecodeError, ValueError):
            return await interaction.followup.send("❌ **Error:** Invalid JSON payload provided.", ephemeral=True)

        # 3. Send the embed
        try:
            embed = discord.Embed.from_dict(embed_data)
            await target_channel.send(embed=embed)
            
            # 4. Update view and send feedback
            embed_msg = self.original_message.embeds[0]
            embed_msg.set_footer(text=_get_admin_footer(interaction, f"Message sent to '{name}'"))
            await _update_setup_embed(self.cog, interaction.guild, embed_msg)
            
            view = SetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).enabled())
            await self.original_message.edit(embed=embed_msg, view=view)
            
            await interaction.followup.send(f"✅ Embed sent successfully to **{name}** ({target_channel.mention}).", ephemeral=True)
            
        except Exception as e:
            log.error(f"Error sending embed: {e}", exc_info=True)
            await interaction.followup.send(f"❌ **Error:** Failed to send embed. Bot may lack permissions. ({e.__class__.__name__})", ephemeral=True)

class RemoveChannelModal(discord.ui.Modal, title="Remove Named Channel"):
    name_input = discord.ui.TextInput(
        label="Configuration Name to Remove",
        style=discord.TextStyle.short,
        placeholder="The name of the channel to remove (e.g., 'general').",
        required=True,
        max_length=50,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        name = self.name_input.value.strip().lower()

        async with self.cog.config.guild(interaction.guild).named_channels() as channels:
            if name in channels:
                del channels[name]
                success = True
            else:
                success = False

        if not success:
            return await interaction.followup.send(f"❌ **Error:** No channel configuration found with the name `{name}`.", ephemeral=True)
        
        # Update the original setup message
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"Channel '{name}' removed"))
        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        view = SetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).enabled())
        await self.original_message.edit(embed=embed, view=view)
        
        await interaction.followup.send(f"✅ Channel configuration **{name}** has been removed.", ephemeral=True)


# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    """A standardized persistent view for Afterwork cog configuration."""
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.initial_enabled = initial_enabled 
        
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

        # Conditionally add configuration buttons if the system is ENABLED
        if initial_enabled:
            self.add_item(self.set_channel_button)
            self.add_item(self.send_message_button)
            self.add_item(self.remove_channel_button)
            
        # Always add the toggle button 
        self.add_item(self.toggle_system)
        
    # Define all buttons using simple methods, but only add them in __init__

    @discord.ui.button(label="Channel ID", style=discord.ButtonStyle.primary, custom_id="mb_set_channel_button", row=0)
    async def set_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Launches the modal to configure and name the target channel ID."""
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
            
        modal = NamedChannelSetModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Message", style=discord.ButtonStyle.primary, custom_id="mb_send_message_button", row=0)
    async def send_message_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Launches the modal to specify the named channel and send the JSON embed."""
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
            
        modal = NamedMessageSendModal(self.cog, interaction.message)
        
        current_json = await self.cog.config.guild(interaction.guild).json_payload()
        
        OLD_TITLE_PAYLOAD = '{"title": "Afterwork Button Embed", "color": 3447003}'
        NEW_TITLE_PAYLOAD = '{"title": "Test Message", "color": 3447003}'
        if current_json == OLD_TITLE_PAYLOAD:
             current_json = NEW_TITLE_PAYLOAD 
        
        modal.json_input.default = current_json
        
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.secondary, custom_id="mb_remove_channel", row=0)
    async def remove_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Launches modal to remove a named channel configuration."""
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        
        modal = RemoveChannelModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Enable/Disable", style=discord.ButtonStyle.secondary, custom_id="mb_toggle_system_main", row=1) 
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggles the system status (Enabled/Disabled)."""
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        new_state = not (await self.cog.config.guild(interaction.guild).enabled())
        await self.cog.config.guild(interaction.guild).enabled.set(new_state)
        
        # 1. Update button style/label
        button.label = "Disable" if new_state else "Enable"
        button.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success
        
        embed = interaction.message.embeds[0]
        status_msg = f"System {'enabled' if new_state else 'disabled'}"
        embed.set_footer(text=_get_admin_footer(interaction, status_msg))
        
        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        # 2. Re-create and edit the view to hide/show config buttons and fields
        new_view = SetupView(self.cog, initial_enabled=new_state)
        await interaction.message.edit(embed=embed, view=new_view) 
        
        await interaction.followup.send(f"System has been **{'enabled' if new_state else 'disabled'}**.", ephemeral=True)


# --- MAIN COG CLASS ---

class AfterworkMB(commands.Cog, name="AfterworkMB"): 
    """
    Manages named channels for sending configured JSON embeds via persistent buttons.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=4466880011, force_registration=True) 
        self.config.register_guild(
            enabled=False,
            setup_message_id=None,
            named_channels={}, 
            json_payload='{"title": "Test Message", "color": 3447003}' 
        )

    async def initialize(self):
        """Loads persistent views on bot restart."""
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                initial_enabled = data.get('enabled', False)
                self.bot.add_view(SetupView(self, initial_enabled=initial_enabled), message_id=data['setup_message_id'])

    @commands.command(name="afterworkmb") 
    @commands.is_owner()
    async def afterworkmb_command(self, ctx: commands.Context):
        """Deploys or redeploys the persistent administrative configuration hub for named channels."""
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

        initial_embed = discord.Embed(title="Send Embed Message", color=discord.Color.blue())
        initial_embed = await _update_setup_embed(self, ctx.guild, initial_embed)
        
        initial_enabled = await self.config.guild(ctx.guild).enabled()
        initial_embed.set_footer(text=_get_admin_footer(ctx, "Configuration Hub Deployed"))

        view = SetupView(self, initial_enabled=initial_enabled)
        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        await sent_message.pin(reason="Afterwork Configuration Hub.")
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
    cog = AfterworkMB(bot) 
    await cog.initialize()
    await bot.add_cog(cog)

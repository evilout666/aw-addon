import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime
import json
from typing import Optional

log = logging.getLogger("red.AfterworkMB") 

# --- UTILITY FUNCTIONS ---

# FIX RETAINED: Function handles both Context and Interaction objects
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
    channel_id = settings.get('target_channel_id') 
    is_enabled = settings.get('enabled', False)

    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    
    target_channel = guild.get_channel(channel_id)
    channel_display = f"**{target_channel.name}** (`{channel_id}`)" if target_channel else "*Not configured*"
    
    embed.description = (
        "Use the buttons to configure the target channel and the embed JSON payload.\n"
        "Click **Send Msg** to open the payload editor and send the final message."
    )
    embed.clear_fields()
    
    embed.add_field(name="System Status", value=status_emoji, inline=False)
    embed.add_field(name="Target Channel", value=channel_display, inline=False)
    
    embed.add_field(
        name="JSON Payload Source", 
        value="Use an Online Editor (e.g., [afterwork.evilout666.com](https://afterwork.evilout666.com)) to generate the message JSON.", 
        inline=False
    )
    
    return embed

# --- MODALS ---

class ChannelIDModal(discord.ui.Modal, title="Set Target Channel ID"):
    channel_id_input = discord.ui.TextInput(
        label="Target Channel ID (Numbers Only)",
        style=discord.TextStyle.short,
        placeholder="ID where the embed will be sent.",
        required=True,
        max_length=20,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        input_channel_id = self.channel_id_input.value.strip()
        
        try:
            channel_id = int(input_channel_id)
        except ValueError:
            return await interaction.followup.send("❌ **Error:** Channel ID must be a valid number.", ephemeral=True)
            
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send(f"❌ **Error:** Could not find a Text Channel with the ID `{channel_id}`.", ephemeral=True)

        # Save configuration
        await self.cog.config.guild(interaction.guild).target_channel_id.set(channel_id)
        
        # Update the original setup message
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, "Target channel updated"))

        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        # Edit message to update the embed
        await self.original_message.edit(embed=embed)
        
        await interaction.followup.send("✅ Target Channel ID saved.", ephemeral=True)


class JSONPayloadModal(discord.ui.Modal, title="Send Embed Message"):
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
        json_payload = self.json_input.value.strip()
        
        settings = await self.cog.config.guild(interaction.guild).all()
        channel_id = settings.get('target_channel_id')
        is_enabled = settings.get('enabled')

        # 1. Validation and early exit checks
        if not is_enabled:
            return await interaction.followup.send("❌ **Error:** System is disabled. Please enable it first.", ephemeral=True)
        if not channel_id:
            return await interaction.followup.send("❌ **Error:** Target Channel ID is not configured. Use the 'Channel ID' button first.", ephemeral=True)

        target_channel = interaction.guild.get_channel(channel_id)
        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            return await interaction.followup.send("❌ **Error:** Configured Target Channel not found or is not a text channel.", ephemeral=True)
            
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
            embed_msg.set_footer(text=_get_admin_footer(interaction, "Embed sent and data updated"))
            await _update_setup_embed(self.cog, interaction.guild, embed_msg)
            # The view is necessary to update the toggle button state and footer if needed
            view = SetupView(self.cog, initial_enabled=is_enabled)
            await self.original_message.edit(embed=embed_msg, view=view)
            
            await interaction.followup.send(f"✅ Embed sent successfully to {target_channel.mention} and JSON payload saved.", ephemeral=True)
            
        except Exception as e:
            log.error(f"Error sending embed: {e}", exc_info=True)
            await interaction.followup.send(f"❌ **Error:** Failed to send embed. Bot may lack permissions. ({e.__class__.__name__})", ephemeral=True)


# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    """A standardized persistent view for Afterwork cog configuration."""
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    # NOTE: The _check_owner function has been removed from this class.
    # The owner check is now done using the standard, async Red function in each button callback.

    @discord.ui.button(label="Channel ID", style=discord.ButtonStyle.primary, custom_id="mb_set_channel_button", row=0)
    async def set_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Launches the modal to configure the target channel."""
        # FIX APPLIED HERE: Using the standard, async Red owner check
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
            
        modal = ChannelIDModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Send Msg", style=discord.ButtonStyle.blurple, custom_id="mb_send_message_button", row=0)
    async def send_message_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Launches the modal to configure and send the JSON embed."""
        # FIX APPLIED HERE: Using the standard, async Red owner check
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
            
        modal = JSONPayloadModal(self.cog, interaction.message)
        
        current_json = await self.cog.config.guild(interaction.guild).json_payload()
        modal.json_input.default = current_json
        
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Enable/Disable", style=discord.ButtonStyle.secondary, custom_id="template_toggle_button", row=0)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        # FIX APPLIED HERE: Using the standard, async Red owner check
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        
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
        
        await interaction.followup.send(f"System has been **{'enabled' if new_state else 'disabled'}**.", ephemeral=True)

# --- MAIN COG CLASS ---

class AfterworkMB(commands.Cog, name="AfterworkMB"): 
    """
    Manages a persistent button to send a configured JSON embed to a target channel.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=4466880011, force_registration=True) 
        self.config.register_guild(
            enabled=False,
            setup_message_id=None,
            target_channel_id=None,
            json_payload='{"title": "Afterwork Button Embed", "color": 3447003}' # Default simple JSON
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
        """Deploys or redeploys the persistent administrative configuration hub for the Message Button."""
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

        initial_embed = discord.Embed(title="Send embed message", color=discord.Color.blue())
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

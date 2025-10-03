import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime
import json
from typing import Optional

log = logging.getLogger("red.AfterworkID") 

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
                title="⚠️ Afterwork ID Error Notification",
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
    message_id = settings.get('target_message_id')
    
    # System Status field is kept but hardcoded for utility cogs
    status_emoji = "🟢 Active" 
    
    target_channel = guild.get_channel(channel_id)
    channel_display = f"**{target_channel.name}** (`{channel_id}`)" if target_channel else "*Not configured*"
    message_display = f"`{message_id}`" if message_id else "*Not fetched yet*"
    
    embed.description = (
        "Use this tool to retrieve the raw JSON data from any message embed.\n"
        "**Step 1:** Set the **Channel ID**. **Step 2:** Use **Message ID** to fetch."
    )
    embed.clear_fields()
    
    embed.add_field(name="System Status", value=status_emoji, inline=False)
    embed.add_field(name="Source Channel", value=channel_display, inline=False)
    embed.add_field(name="Last Fetched Message ID", value=message_display, inline=False)
    
    return embed

# --- MODALS ---

class ChannelIDSetModal(discord.ui.Modal, title="Set Source Channel ID"):
    channel_id_input = discord.ui.TextInput(
        label="Source Channel ID",
        style=discord.TextStyle.short,
        placeholder="ID of the channel where messages will be fetched from.",
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

        await self.cog.config.guild(interaction.guild).target_channel_id.set(channel_id)
        
        embed_msg = self.original_message.embeds[0]
        embed_msg.set_footer(text=_get_admin_footer(interaction, "Source Channel set"))
        await _update_setup_embed(self.cog, interaction.guild, embed_msg)
        
        # Use initial_enabled=False since the cog no longer tracks 'enabled' state
        view = SetupView(self.cog, initial_enabled=False) 
        await self.original_message.edit(embed=embed_msg, view=view)
        await interaction.followup.send(f"✅ Source Channel set to `{channel.name}`.", ephemeral=True)


class MessageIDModal(discord.ui.Modal, title="Fetch Embed JSON"):
    message_id_input = discord.ui.TextInput(
        label="Message ID",
        style=discord.TextStyle.short,
        placeholder="ID of the message containing the embed.",
        required=True,
        max_length=20,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        input_message_id = self.message_id_input.value.strip()
        
        # 1. Get the saved Channel ID
        saved_channel_id = await self.cog.config.guild(interaction.guild).target_channel_id()
        
        if not saved_channel_id:
            return await interaction.followup.send("❌ **Error:** Source Channel ID is not set. Use the 'Channel ID' button first.", ephemeral=True)
        
        try:
            message_id = int(input_message_id)
        except ValueError:
            return await interaction.followup.send("❌ **Error:** Message ID must be a valid number.", ephemeral=True)
            
        channel = interaction.guild.get_channel(saved_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send(f"❌ **Error:** Saved Channel (`{saved_channel_id}`) is invalid or no longer exists.", ephemeral=True)
            
        # 2. Fetch the message
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await interaction.followup.send("❌ **Error:** Message not found in the set channel.", ephemeral=True)
        except discord.Forbidden:
            return await interaction.followup.send("❌ **Error:** Bot lacks permissions to read messages in that channel.", ephemeral=True)
        except Exception:
            return await interaction.followup.send("❌ **Error:** Failed to fetch message.", ephemeral=True)

        # 3. Check for embed
        if not message.embeds:
            return await interaction.followup.send("❌ **Error:** The specified message does not contain any embeds.", ephemeral=True)

        # 4. Get the JSON and format
        embed_dict = message.embeds[0].to_dict()
        embed_json = json.dumps(embed_dict, indent=4)
        
        # 5. Save the Message ID
        await self.cog.config.guild(interaction.guild).target_message_id.set(message_id)
        
        # 6. Update setup message
        embed_msg = self.original_message.embeds[0]
        embed_msg.set_footer(text=_get_admin_footer(interaction, "Embed JSON fetched"))
        await _update_setup_embed(self.cog, interaction.guild, embed_msg)
        
        view = SetupView(self.cog, initial_enabled=await self.cog.config.guild(interaction.guild).enabled())
        await self.original_message.edit(embed=embed_msg, view=view)
        
        # 7. Send JSON response
        if len(embed_json) < 1990:
            content = f"✅ Embed JSON fetched successfully:\n```json\n{embed_json}\n```"
        else:
            content = f"✅ Embed JSON fetched successfully (too long for code block, sent raw):\n{embed_json}"

        await interaction.followup.send(content, ephemeral=True)


# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    """A standardized persistent view for Afterwork cog configuration."""
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        
        # Initial enabled state is no longer used for the clear button
        # self.toggle_system is replaced by clear_channel_id

    @discord.ui.button(label="Channel ID", style=discord.ButtonStyle.primary, custom_id="id_set_channel_button", row=0)
    async def set_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Launches the modal to set the source channel ID."""
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
            
        modal = ChannelIDSetModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Message ID", style=discord.ButtonStyle.secondary, custom_id="id_fetch_message_button", row=0)
    async def fetch_message_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Launches the modal to input message ID and fetch JSON."""
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
            
        modal = MessageIDModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Clear", style=discord.ButtonStyle.danger, custom_id="id_clear_button", row=0)
    async def clear_channel_id(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Clears the saved Channel ID and Message ID."""
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        await self.cog.config.guild(interaction.guild).target_channel_id.set(None)
        await self.cog.config.guild(interaction.guild).target_message_id.set(None)
        
        embed = interaction.message.embeds[0]
        status_msg = "Saved IDs cleared"
        embed.set_footer(text=_get_admin_footer(interaction, status_msg))
        
        await _update_setup_embed(self.cog, interaction.guild, embed)
        # Re-create the view with initial_enabled=False for consistent structure
        view = SetupView(self.cog, initial_enabled=False) 
        await interaction.message.edit(embed=embed, view=view)
        
        await interaction.followup.send("✅ Saved Channel and Message IDs have been cleared.", ephemeral=True)

# --- MAIN COG CLASS ---

class AfterworkID(commands.Cog, name="AfterworkID"): 
    """
    Utility cog to fetch the raw JSON dictionary from a Discord message embed.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5577991122, force_registration=True) 
        self.config.register_guild(
            # 'enabled' is kept for Red structure but unused for button logic
            enabled=False, 
            setup_message_id=None,
            target_channel_id=None, 
            target_message_id=None, 
        )

    async def initialize(self):
        """Loads persistent views on bot restart."""
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                initial_enabled = data.get('enabled', False)
                self.bot.add_view(SetupView(self, initial_enabled=initial_enabled), message_id=data['setup_message_id'])

    @commands.command(name="afterworkid") 
    @commands.is_owner()
    async def afterworkid_command(self, ctx: commands.Context):
        """Deploys or redeploys the persistent administrative configuration hub for fetching embed JSON."""
        
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

        initial_embed = discord.Embed(title="Fetch Embed JSON Utility", color=discord.Color.blue())
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
    cog = AfterworkID(bot) 
    await cog.initialize()
    await bot.add_cog(cog)

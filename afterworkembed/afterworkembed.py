import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime
import json
from typing import Union

log = logging.getLogger("red.AfterworkEmbed") 

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
    owner_id = bot.owner_id
    owner = bot.get_user(owner_id)
    if owner:
        try:
            embed = discord.Embed(
                title="⚠️ Afterwork Embed Error Notification",
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
    
    channel_list = [
        f"• **{name}** -> {f'#{guild.get_channel(channel_id).name}' if guild.get_channel(channel_id) else 'Unknown Channel'} (`{channel_id}`)"
        for name, channel_id in named_channels.items()
    ]
    channel_list_display = "\n".join(channel_list) or "*No named channels configured*"
    
    embed.description = "Configure named channels to quickly send custom JSON embeds."
    embed.clear_fields()
    embed.add_field(name="Configured Channels", value=channel_list_display, inline=False)
    embed.add_field(
        name="How to Use", 
        value="1. **Set Named Channel:** Save a channel with a short name.\n"
              "2. **Send Embed:** Use the saved name and a JSON payload to send a message.", 
        inline=False
    )
    
    return embed

# --- MODALS ---

class NamedChannelSetModal(discord.ui.Modal, title="Set or Update a Named Channel"):
    name_input = discord.ui.TextInput(label="Unique Name (e.g., 'announcements')", style=discord.TextStyle.short, required=True, max_length=50)
    channel_id_input = discord.ui.TextInput(label="Channel ID", style=discord.TextStyle.short, required=True, max_length=20)
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300); self.cog = cog; self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        name = self.name_input.value.strip().lower()
        
        try:
            channel_id = int(self.channel_id_input.value.strip())
        except ValueError:
            # User error: Invalid ID input
            return await interaction.followup.send("❌ **Error:** Channel ID must be a valid number.", ephemeral=True)
            
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            # User error: Channel not found or not a text channel
            return await interaction.followup.send(f"❌ **Error:** Could not find a Text Channel with the ID `{channel_id}`.", ephemeral=True)

        async with self.cog.config.guild(interaction.guild).named_channels() as channels:
            channels[name] = channel_id
        
        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"Channel '{name}' updated"))
        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        await self.original_message.edit(embed=embed, view=SetupView(self.cog))
        # Success message removed

class NamedMessageSendModal(discord.ui.Modal, title="Send Embed to Named Channel"):
    name_input = discord.ui.TextInput(label="Configuration Name", style=discord.TextStyle.short, placeholder="The name of the saved channel (e.g., 'announcements').", required=True, max_length=50)
    json_input = discord.ui.TextInput(label="JSON Embed Payload", style=discord.TextStyle.long, placeholder='{"title": "Title", "description": "Text"}', required=True)
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300); self.cog = cog; self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        name = self.name_input.value.strip().lower()
        
        settings = await self.cog.config.guild(interaction.guild).all()
        channel_id = settings.get('named_channels', {}).get(name)
        
        if not channel_id:
            return await interaction.followup.send(f"❌ **Error:** No channel found with the name `{name}`.", ephemeral=True)
        
        target_channel = interaction.guild.get_channel(channel_id)
        if not target_channel:
            return await interaction.followup.send(f"❌ **Error:** The channel for `{name}` is invalid or has been deleted.", ephemeral=True)
            
        try:
            embed_data = json.loads(self.json_input.value.strip())
            embed = discord.Embed.from_dict(embed_data)
            await target_channel.send(embed=embed)
            await self.cog.config.guild(interaction.guild).json_payload.set(self.json_input.value.strip())
            # Success confirmation removed
        except (json.JSONDecodeError, ValueError):
            return await interaction.followup.send("❌ **Error:** Invalid JSON payload provided.", ephemeral=True)
        except Exception as e:
            # System error: Send to owner via DM
            await _send_owner_dm(self.cog.bot, f"Failed to send embed to {target_channel.mention} in {interaction.guild.name}: {e}")
            return await interaction.followup.send("❌ **Error:** Failed to send embed. Check DMs for details.", ephemeral=True)

class RemoveChannelModal(discord.ui.Modal, title="Remove Named Channel"):
    name_input = discord.ui.TextInput(label="Configuration Name to Remove", style=discord.TextStyle.short, required=True, max_length=50)
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300); self.cog = cog; self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        name = self.name_input.value.strip().lower()

        async with self.cog.config.guild(interaction.guild).named_channels() as channels:
            if name not in channels:
                # User error: Channel name not found
                return await interaction.followup.send(f"❌ **Error:** No channel configuration found with the name `{name}`.", ephemeral=True)
            del channels[name]

        embed = self.original_message.embeds[0]
        embed.set_footer(text=_get_admin_footer(interaction, f"Channel '{name}' removed"))
        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        await self.original_message.edit(embed=embed, view=SetupView(self.cog))
        # Success confirmation removed


# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Set Named Channel", style=discord.ButtonStyle.primary, custom_id="embed_set_channel_button", row=0)
    async def set_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        await interaction.response.send_modal(NamedChannelSetModal(self.cog, interaction.message))

    @discord.ui.button(label="Send Embed", style=discord.ButtonStyle.success, custom_id="embed_send_message_button", row=0)
    async def send_message_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
            
        modal = NamedMessageSendModal(self.cog, interaction.message)
        modal.json_input.default = await self.cog.config.guild(interaction.guild).json_payload()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove Named Channel", style=discord.ButtonStyle.danger, custom_id="embed_remove_channel", row=0)
    async def remove_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): 
            return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        await interaction.response.send_modal(RemoveChannelModal(self.cog, interaction.message))

# --- MAIN COG CLASS ---

class AfterworkEmbed(commands.Cog, name="AfterworkEmbed"): 
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=4466880011, force_registration=True) 
        self.config.register_guild(
            setup_message_id=None,
            named_channels={}, 
            json_payload='{"title": "Example Embed", "description": "Hello, world!", "color": 3447003}' 
        )

    async def initialize(self):
        """Loads persistent views on bot restart."""
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                self.bot.add_view(SetupView(self), message_id=data['setup_message_id'])

    @commands.group(name="afterworkembed")
    @commands.is_owner()
    async def afterworkembed_group(self, ctx: commands.Context):
        """Management commands for the AfterworkEmbed cog."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @afterworkembed_group.command(name="deploy")
    async def afterworkembed_deploy(self, ctx: commands.Context):
        """Deploys or redeploys the persistent administrative configuration hub."""
        bot_member = ctx.guild.me
        if not bot_member.guild_permissions.manage_messages:
            return await _send_owner_dm(self.bot, f"Config failed in **{ctx.guild.name}**. Need Send/Manage Messages in **#{ctx.channel.name}**.")

        old_message_id = await self.config.guild(ctx.guild).setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException: pass

        initial_embed = discord.Embed(title="Custom Embed Sender", color=discord.Color.blue())
        initial_embed = await _update_setup_embed(self, ctx.guild, initial_embed)
        initial_embed.set_footer(text=_get_admin_footer(ctx, "Configuration Hub Deployed"))

        view = SetupView(self)
        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        await sent_message.pin(reason="Afterwork Embed Configuration Hub.")
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
    cog = AfterworkEmbed(bot) 
    await cog.initialize()
    await bot.add_cog(cog)

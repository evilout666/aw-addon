import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime

log = logging.getLogger("red.AfterworkTV")

# --- UTILITY FUNCTIONS (SHARED HELPERS) ---

async def _send_owner_dm(bot, message: str):
    """Sends a critical error message directly to the bot owner."""
    owner_id = bot.owner_id
    owner = bot.get_user(owner_id)
    if owner:
        try:
            embed = discord.Embed(
                title="⚠️ Afterwork TV Error Notification",
                description=message,
                color=discord.Color.red()
            )
            await owner.send(embed=embed)
        except discord.Forbidden:
            log.error(f"Failed to DM owner ({owner.name}). Owner must enable DMs.")

async def _update_setup_embed(cog: commands.Cog, guild: discord.Guild, embed: discord.Embed):
    """Refreshes the configuration data shown in the setup embed."""
    settings = await cog.config.guild(guild).all()
    source_id = settings.get('source_channel')
    dest_id = settings.get('dest_channel')
    is_enabled = settings.get('enabled', False)

    source_channel = cog.bot.get_channel(source_id)
    dest_channel = cog.bot.get_channel(dest_id)
    
    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    source_name = f"**{source_channel.name}** (`{source_id}`)" if source_channel else "*Not yet configured*"
    dest_name = f"**{dest_channel.name}** (`{dest_id}`)" if dest_channel else "*Not yet configured*"
    
    embed.description = "Use this panel to manage the Sonarr/Radarr webhook reformatter."
    embed.clear_fields()
    
    embed.add_field(name="System Status", value=status_emoji, inline=True)
    embed.add_field(name="Source Channel (Webhook Input)", value=source_name, inline=False)
    embed.add_field(name="Destination Channel (Clean Output)", value=dest_name, inline=False)
    
    return embed

# --- MODAL (The Fill-in Box for Channel IDs) ---

class ChannelIDModal(discord.ui.Modal, title="Set Webhook Channels"):
    """A Modal to collect both Source and Destination Channel IDs."""
    
    source_channel_id_input = discord.ui.TextInput(
        label="Source Channel ID (Webhook Input)",
        style=discord.TextStyle.short,
        placeholder="Paste the ID of the channel where webhooks arrive.",
        required=True,
        max_length=20,
    )
    
    dest_channel_id_input = discord.ui.TextInput(
        label="Destination Channel ID (Clean Output)",
        style=discord.TextStyle.short,
        placeholder="Paste the ID of the channel for the clean embeds.",
        required=True,
        max_length=20,
    )
    
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        source_input_id = self.source_channel_id_input.value.strip()
        dest_input_id = self.dest_channel_id_input.value.strip()
        
        try:
            source_id = int(source_input_id)
            dest_id = int(dest_input_id)
        except ValueError:
            return await interaction.response.send_message("❌ **Error:** Both inputs must be valid channel IDs (numbers only).", ephemeral=True)
        
        source_channel = interaction.guild.get_channel(source_id)
        dest_channel = interaction.guild.get_channel(dest_id)

        if not source_channel or not isinstance(source_channel, discord.TextChannel):
            return await interaction.response.send_message(f"❌ **Error:** Could not find a Text Channel with the Source ID `{source_id}`.", ephemeral=True)
        
        if not dest_channel or not isinstance(dest_channel, discord.TextChannel):
            return await interaction.response.send_message(f"❌ **Error:** Could not find a Text Channel with the Destination ID `{dest_id}`.", ephemeral=True)

        # Save configuration
        await self.cog.config.guild(interaction.guild).source_channel.set(source_id)
        await self.cog.config.guild(interaction.guild).dest_channel.set(dest_id)
        await self.cog.config.guild(interaction.guild).enabled.set(True) # Auto-enable on new config
        
        # Update the hub message
        embed = self.original_message.embeds[0]
        embed.set_footer(text=f"Last updated by {interaction.user.display_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        await _update_setup_embed(self.cog, interaction.guild, embed)
        
        view = SetupView(self.cog, initial_enabled=True)
        await interaction.response.edit_message(embed=embed, view=view)

# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    """A persistent view for the TV cog's interactive hub."""
    
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    @discord.ui.button(label="Set Channels", style=discord.ButtonStyle.primary, custom_id="tv_set_channels_button", row=0)
    async def set_channels_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only the bot owner can use this setup tool.", ephemeral=True)
        modal = ChannelIDModal(self.cog, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Toggle System", style=discord.ButtonStyle.secondary, custom_id="tv_toggle_button", row=0)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user):
            return await interaction.response.send_message("Only the bot owner can use this toggle.", ephemeral=True)
        
        new_state = not (await self.cog.config.guild(interaction.guild).enabled())
        await self.cog.config.guild(interaction.guild).enabled.set(new_state)
        
        button.label = "Disable" if new_state else "Enable"
        button.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success

        embed = interaction.message.embeds[0]
        embed.set_footer(text=f"Status toggled by {interaction.user.display_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        await _update_setup_embed(self.cog, interaction.guild, embed)

        await interaction.response.edit_message(embed=embed, view=self)

# --- MAIN COG CLASS ---

class AfterworkTV(commands.Cog, name="AfterworkTV"):
    """
    Reformats and reposts Sonarr/Radarr webhook embeds to a clean channel.
    Configuration is handled via a persistent interactive hub message.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)
        self.config.register_guild(
            enabled=False,
            source_channel=None,
            dest_channel=None,
            setup_message_id=None
        )

    async def initialize(self):
        """Asynchronously sets up persistent views on bot startup."""
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                initial_enabled = data.get('enabled', False)
                self.bot.add_view(SetupView(self, initial_enabled=initial_enabled), message_id=data['setup_message_id'])

    @commands.command(name="afterworktv")
    @commands.is_owner()
    async def afterworktv_command(self, ctx: commands.Context):
        """Posts the permanent interactive configuration hub for Afterwork TV."""
        bot_member = ctx.guild.get_member(self.bot.user.id)
        perms = ctx.channel.permissions_for(bot_member)
        if not perms.send_messages or not perms.manage_messages:
            await _send_owner_dm(self.bot, 
                f"Configuration failed in **{ctx.guild.name}**. I need **Send Messages** and **Manage Messages** permissions in **#{ctx.channel.name}** to post the hub."
            )
            return

        old_message_id = await self.config.guild(ctx.guild).setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException:
                pass

        initial_embed = discord.Embed(title="🎬 Sonarr & Radarr Configuration", color=discord.Color.blue())
        initial_embed = await _update_setup_embed(self, ctx.guild, initial_embed)
        
        initial_enabled = await self.config.guild(ctx.guild).enabled()
        view = SetupView(self, initial_enabled=initial_enabled)

        sent_message = await ctx.send(embed=initial_embed, view=view)
        
        await sent_message.pin(reason="Afterwork TV Configuration Hub.")
        await self.config.guild(ctx.guild).setup_message_id.set(sent_message.id)
        
        await ctx.message.delete()
        
        await asyncio.sleep(1) 
        try:
            async for message in ctx.channel.history(limit=5):
                if message.type == discord.MessageType.pins_add and message.author.id == self.bot.user.id:
                    await message.delete()
                    break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not message.embeds or not message.author.bot:
            return
        
        data = await self.config.guild(message.guild).all()
        if not data.get('enabled') or message.channel.id != data.get('source_channel'):
            return

        dest_id = data.get('dest_channel')
        if not dest_id:
            return

        dest_channel = self.bot.get_channel(dest_id)
        if not dest_channel:
            return

        for emb in message.embeds:
            footer = (emb.footer.text or "") if emb.footer else ""
            if "Sonarr" in footer or "Radarr" in footer:
                new_embed = discord.Embed(
                    title=emb.title, 
                    description=emb.description, 
                    color=emb.color
                )
                if emb.thumbnail:
                    new_embed.set_thumbnail(url=emb.thumbnail.url)
                
                try:
                    await dest_channel.send(embed=new_embed)
                except discord.Forbidden:
                    error_msg = (
                        f"Failed to repost webhook embed in **{message.guild.name}**.\n"
                        f"I lack **Send Messages** or **Embed Links** permission in the destination channel: {dest_channel.mention}."
                    )
                    await _send_owner_dm(self.bot, error_msg)
                    # Disable the cog for this guild to prevent spamming DMs
                    await self.config.guild(message.guild).enabled.set(False)
                except Exception as e:
                    log.exception(f"An unexpected error occurred while forwarding an embed: {e}")

async def setup(bot):
    """The function Red uses to load the cog."""
    cog = AfterworkTV(bot)
    await cog.initialize()
    await bot.add_cog(cog)



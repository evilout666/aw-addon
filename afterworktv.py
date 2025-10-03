import discord
from redbot.core import commands, Config
import logging
import asyncio
import re
from datetime import datetime

log = logging.getLogger("red.AfterworkTV")

# --- UTILITY FUNCTIONS ---

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
    dest_id = settings.get('dest_channel')
    user_id = settings.get('webhook_user_id')
    is_enabled = settings.get('enabled', False)

    dest_channel = cog.bot.get_channel(dest_id)
    # We can't reliably get a user object for a webhook, so we just display the ID
    webhook_user_display = f"`{user_id}`" if user_id else "*Not configured*"
    
    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    dest_name = f"**{dest_channel.name}** (`{dest_id}`)" if dest_channel else "*Not configured*"
    
    embed.description = "Use this panel to manage the webhook reformatter."
    embed.clear_fields()
    
    embed.add_field(name="System Status", value=status_emoji, inline=True)
    embed.add_field(name="Webhook User ID", value=webhook_user_display, inline=False)
    embed.add_field(name="Destination Channel", value=dest_name, inline=False)
    
    return embed

# --- MODALS ---

class TargetChannelModal(discord.ui.Modal, title="Set Target Channel"):
    channel_id_input=discord.ui.TextInput(label="Target Channel ID",style=discord.TextStyle.short,placeholder="Paste the ID of the channel for clean embeds.",required=True,max_length=20)
    def __init__(self,cog:commands.Cog,original_message:discord.Message):super().__init__(timeout=300);self.cog=cog;self.original_message=original_message
    async def on_submit(self,interaction:discord.Interaction):
        input_id=self.channel_id_input.value.strip()
        try:channel_id=int(input_id)
        except ValueError:return await interaction.response.send_message("❌ Invalid ID.",ephemeral=True)
        channel=interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel,discord.TextChannel):return await interaction.response.send_message(f"❌ Text Channel not found.",ephemeral=True)
        await self.cog.config.guild(interaction.guild).dest_channel.set(channel_id)
        embed=self.original_message.embeds[0]
        embed.set_footer(text=f"Target updated by {interaction.user.display_name}")
        await _update_setup_embed(self.cog,interaction.guild,embed)
        await interaction.response.edit_message(embed=embed)

class UserIDModal(discord.ui.Modal, title="Set Webhook User ID"):
    user_id_input = discord.ui.TextInput(
        label="Webhook User/Bot ID",
        style=discord.TextStyle.short,
        placeholder="Paste the ID of the user that posts webhooks.",
        required=True,
        max_length=20,
    )
    def __init__(self, cog: commands.Cog, original_message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.original_message = original_message
    async def on_submit(self, interaction: discord.Interaction):
        input_id = self.user_id_input.value.strip()
        try:
            user_id = int(input_id)
        except ValueError:
            return await interaction.response.send_message("❌ **Error:** Input must be a valid numerical ID.", ephemeral=True)
        
        await self.cog.config.guild(interaction.guild).webhook_user_id.set(user_id)
        embed = self.original_message.embeds[0]
        embed.set_footer(text=f"User ID updated by {interaction.user.display_name}")
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await interaction.response.edit_message(embed=embed)

# --- VIEW (The Persistent Setup Hub) ---

class SetupView(discord.ui.View):
    """A persistent view for the TV cog's interactive hub."""
    
    def __init__(self, cog: commands.Cog, initial_enabled: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.toggle_system.label = "Disable" if initial_enabled else "Enable"
        self.toggle_system.style = discord.ButtonStyle.danger if initial_enabled else discord.ButtonStyle.success

    @discord.ui.button(label="Set Target", style=discord.ButtonStyle.primary, custom_id="tv_set_target_button", row=0)
    async def set_target_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        await interaction.response.send_modal(TargetChannelModal(self.cog, interaction.message))

    @discord.ui.button(label="Set User ID", style=discord.ButtonStyle.primary, custom_id="tv_set_user_id_button", row=0)
    async def set_user_id_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        await interaction.response.send_modal(UserIDModal(self.cog, interaction.message))

    @discord.ui.button(label="Enable/Disable", style=discord.ButtonStyle.secondary, custom_id="tv_toggle_button", row=1)
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.bot.is_owner(interaction.user): return await interaction.response.send_message("Only owner can use this.", ephemeral=True)
        new_state = not (await self.cog.config.guild(interaction.guild).enabled())
        await self.cog.config.guild(interaction.guild).enabled.set(new_state)
        button.label = "Disable" if new_state else "Enable"
        button.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success
        embed = interaction.message.embeds[0]
        embed.set_footer(text=f"System status toggled by {interaction.user.display_name}")
        await _update_setup_embed(self.cog, interaction.guild, embed)
        await interaction.response.edit_message(embed=embed, view=self)

# --- MAIN COG CLASS ---

class AfterworkTV(commands.Cog, name="AfterworkTV"):
    """
    Reformats and reposts Sonarr/Radarr webhook embeds, with intelligent season grouping.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=987654321, force_registration=True)
        self.config.register_guild(
            enabled=False,
            dest_channel=None,
            webhook_user_id=None,
            setup_message_id=None,
            group_season_grabs=True,
            grouping_delay=300
        )
        self.grab_buffer = {}

    async def initialize(self):
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                initial_enabled = data.get('enabled', False)
                self.bot.add_view(SetupView(self, initial_enabled=initial_enabled), message_id=data['setup_message_id'])

    async def _debounce_sonarr_post(self, guild_id: int, series_title: str, season_num: int, original_embed: discord.Embed):
        # NOTE FOR TESTING: This value is temporarily set to 1 second.
        # For production, it should be reverted to settings.get('grouping_delay', 300).
        delay = 1 
        await asyncio.sleep(delay)

        dest_id = await self.config.guild_from_id(guild_id).dest_channel()
        if not dest_id: return
        dest_channel = self.bot.get_channel(dest_id)
        if not dest_channel: return

        new_embed = discord.Embed(title=f"{series_title} - Season {season_num}",description=f"Season {season_num} of **{series_title}** has been added to the library.",color=original_embed.color)
        if original_embed.thumbnail: new_embed.set_thumbnail(url=original_embed.thumbnail.url)
        try:
            await dest_channel.send(embed=new_embed)
        except discord.Forbidden: pass 
        finally:
            self.grab_buffer.pop((guild_id, series_title, season_num), None)

    @commands.command(name="afterworktv")
    @commands.is_owner()
    async def afterworktv_command(self, ctx: commands.Context):
        bot_member = ctx.guild.get_member(self.bot.user.id)
        perms = ctx.channel.permissions_for(bot_member)
        if not perms.send_messages or not perms.manage_messages:
            await _send_owner_dm(self.bot, f"Config failed in **{ctx.guild.name}**. Need Send/Manage Messages in **#{ctx.channel.name}**.")
            return
        old_message_id = await self.config.guild(ctx.guild).setup_message_id()
        if old_message_id:
            try:
                old_message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException: pass
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
        except Exception: pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not message.embeds: return
        data = await self.config.guild(message.guild).all()
        webhook_user_id = data.get('webhook_user_id')
        if not data.get('enabled') or not webhook_user_id or message.author.id != webhook_user_id:
            return
            
        grouping_enabled = data.get('group_season_grabs', True)

        for emb in message.embeds:
            # This pattern handles both "S01E01" and "19x01" formats.
            match = re.match(r"^(.*?) - (?:S)?(\d+)[xE](\d+)", emb.title or "")

            if match and grouping_enabled:
                series_title = match.group(1).strip()
                season_num = int(match.group(2))
                buffer_key = (message.guild.id, series_title, season_num)
                if buffer_key in self.grab_buffer:
                    log.info(f"Suppressing duplicate Sonarr grab for {series_title} S{season_num}.")
                    continue
                log.info(f"Starting debounce for {series_title} S{season_num}.")
                task = asyncio.create_task(self._debounce_sonarr_post(message.guild.id, series_title, season_num, emb))
                self.grab_buffer[buffer_key] = task
            else:
                log.info("Processing as a direct post (Movie, non-standard, or grouping disabled).")
                new_embed=discord.Embed(title=emb.title,description=emb.description,color=emb.color)
                if emb.thumbnail:new_embed.set_thumbnail(url=emb.thumbnail.url)
                dest_channel=self.bot.get_channel(data.get('dest_channel'))
                if dest_channel:
                    try:
                        sent_msg = await dest_channel.send(embed=new_embed)
                        log.info(f"Reposted webhook. ID: {sent_msg.id}")
                    except discord.Forbidden: 
                        await _send_owner_dm(self.bot, f"Failed to post embed in {dest_channel.mention} due to permissions.")

async def setup(bot):
    cog = AfterworkTV(bot)
    await cog.initialize()
    await bot.add_cog(cog)


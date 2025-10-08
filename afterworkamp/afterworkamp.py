'''
   Copyright (C) 2021-2022 Katelynn Cadwallader.
   This file is part of AfterworkAMP, the custom AMP Discord Bot cog.
   This cog enables multi-instance status updates without requiring the
   per-instance Developer License to load unsigned plugins.
'''
import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import logging
from datetime import datetime, timezone

# NOTE: These modules (utils, AMP, DB) are assumed to be available
# and correctly configured by your RedBot/Gatekeeper environment.
import utils 
import AMP as AMP
import DB as DB

# --- CONFIGURATION (PLACEHOLDER) ---
# NOTE: This will be overridden by the 'setstatuschannel' command after first run.
GLOBAL_DEFAULT_CHANNEL_ID = 123456789012345678 # <<< REPLACE with a valid channel ID for initial setup
STATUS_UPDATE_INTERVAL_SECONDS = 30 

class AfterworkAMP(commands.Cog):
    """
    Manages AMP server status and player count updates on Discord 
    for all registered instances using the AMP API.
    """
    def __init__ (self, client: discord.Client):
        self._client = client
        self.name = 'AfterworkAMP' 
        self.logger = logging.getLogger(self.name) 
        self.logger.info(f'Initializing Module {self.name}')

        # --- AMP HANDLERS ---
        self.AMPHandler = AMP.getAMPHandler()
        self.AMPInstances = self.AMPHandler.AMP_Instances 
        
        # --- DB AND UTILITY HANDLERS ---
        self.DBHandler = DB.getDBHandler()
        self.DBCOnfig = self.DBHandler.DB.DBConfig # Assumes your config is here
        self.uBot = utils.botUtils(client)
        self.dBot = utils.discordBot(client)

        # Stores {instance_name: message_id} for editing embeds
        self.status_messages = {}

        self.update_server_status_loop.start()

        self.logger.info(f'**SUCCESS** Loading Module **{self.name}**')

    def cog_unload(self):
        """Clean up when the cog is unloaded."""
        self.update_server_status_loop.cancel()
        self.logger.info(f'**UNLOADED** Module **{self.name}**')

    def get_instance_info(self, instance_data):
        """Extracts and formats status and player info."""
        
        status = instance_data.get('Status', 'UNKNOWN')
        status_emoji = '❓'
        color = 0x808080 
        
        if status == 'Running':
            status_emoji = '🟢'
            color = 0x32CD32 
        elif status == 'Stopped':
            status_emoji = '🔴'
            color = 0xFF0000
        elif status in ('Starting', 'ShuttingDown', 'Updating'):
            status_emoji = '🟡'
            color = 0xFFA500
        
        try:
            player_count = instance_data.get('Players', 0)
            max_players = instance_data.get('MaxPlayers', '?')
        except:
            player_count = 0
            max_players = '?'

        return status, status_emoji, player_count, max_players, color

    async def build_status_embed(self, instance_name: str, instance_data: dict) -> discord.Embed:
        """Creates the Discord embed for a single server status."""
        
        status, status_emoji, player_count, max_players, color = self.get_instance_info(instance_data)
        
        embed = discord.Embed(
            title=f"{status_emoji} {instance_name} | Status: {status}",
            color=color
        )

        embed.add_field(
            name="Players Online",
            value=f"`{player_count}/{max_players}`",
            inline=True
        )

        connection_url = instance_data.get('ConnectURL', 'Connect via Server List')
        embed.add_field(
            name="Connection Info",
            value=f"```\n{connection_url}\n```",
            inline=False
        )
        
        embed.set_footer(text=f"Last Updated: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")

        return embed

    @tasks.loop(seconds=STATUS_UPDATE_INTERVAL_SECONDS)
    async def update_server_status_loop(self):
        """The main loop that checks all AMP servers and updates their Discord embeds and bot presence."""
        
        await self._client.wait_until_ready() 
        
        total_online_servers = 0
        total_players = 0
        
        for instance_name, instance_data in self.AMPInstances.items():
            
            # --- DYNAMIC CHANNEL RETRIEVAL ---
            # Attempt to get the specific channel ID saved for this instance
            target_channel_id = self.DBCOnfig.get(instance_name, {}).get('status_channel_id', GLOBAL_DEFAULT_CHANNEL_ID)
            
            if not target_channel_id:
                self.logger.warning(f"No channel configured for {instance_name}. Skipping update.")
                continue 
            
            channel = self._client.get_channel(target_channel_id)
            if not channel:
                self.logger.warning(f"Configured channel {target_channel_id} not found for {instance_name}. Skipping update.")
                continue
                
            try:
                # --- Update Embed Message ---
                embed = await self.build_status_embed(instance_name, instance_data)
                
                # Update counters
                if instance_data.get('Status') == 'Running':
                    total_online_servers += 1
                    total_players += instance_data.get('Players', 0)
                
                message_id = self.status_messages.get(instance_name)
                
                if message_id:
                    # Edit existing message
                    message = await self.dBot.get_message(channel.id, message_id)
                    await self.dBot.edit_message(message, embed=embed)
                else:
                    # Post new message and save its ID
                    message = await self.dBot.send_message(channel.id, embed=embed)
                    self.status_messages[instance_name] = message.id
                    
            except Exception as e:
                self.logger.error(f"Error updating status for {instance_name}: {e}")
                
        # --- Update RedBot's Presence (Status) ---
        await self._client.change_presence(
            activity=discord.Game(
                name=f"Monitoring {total_online_servers}/7 Servers | {total_players} Players"
            ),
            status=discord.Status.online
        )

    # --- MANAGEMENT COMMANDS ---

    @commands.hybrid_command(name='setstatuschannel')
    @utils.role_check() 
    @app_commands.describe(
        server_name='The name of the AMP instance (e.g., ARK1, ARK2)',
        channel='The Discord channel to post the status embed in'
    )
    async def set_status_channel(self, context: commands.Context, server_name: str, channel: discord.TextChannel):
        """Sets the Discord channel where a specific server's status embed will be posted."""
        
        # 1. Input Validation: Check if the AMP instance name is valid
        if server_name not in self.AMPInstances:
            return await context.send(f"Error: AMP server **{server_name}** not found in the managed instances.", ephemeral=True)

        # 2. Store the setting (NOTE: You must ensure this save method is correctly implemented)
        try:
            # We save the channel ID tied to the instance name
            # This logic assumes the DBHandler exposes a method to set nested instance config:
            self.DBCOnfig.get(server_name, {})['status_channel_id'] = channel.id
            
            # Reset stored message ID to force a new post in the new channel
            if server_name in self.status_messages:
                 del self.status_messages[server_name]
            
            # Force an update to instantly post the new embed
            await self.update_server_status_loop()
            
            await context.send(
                f"Status channel for **{server_name}** successfully set to {channel.mention}. Embed will appear shortly.", 
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error saving channel setting for {server_name}: {e}")
            await context.send("Error saving channel setting. Please check your DB implementation.", ephemeral=True)

    @commands.hybrid_command(name='ampstatus')
    @utils.role_check()
    async def amp_status_cmd(self, context: commands.Context):
        """Forces an immediate update of all server status embeds."""
        await context.defer()
        await self.update_server_status_loop()
        await context.send("Server status update forced.", ephemeral=True)

# Final step to load the cog
async def setup(client):
    await client.add_cog(AfterworkAMP(client))

# New command to set the destination channel for a server's status embed
    @commands.hybrid_command(name='setstatuschannel')
    @utils.role_check() # Ensure only owners/admins can use this
    @app_commands.describe(
        server_name='The name of the AMP instance (e.g., ARK1, ARK2)',
        channel='The Discord channel to post the status embed in'
    )
    async def set_status_channel(self, context: commands.Context, server_name: str, channel: discord.TextChannel):
        """Sets the Discord channel where a specific server's status embed will be posted."""
        
        # 1. Input Validation: Check if the AMP instance name is valid
        if server_name not in self.AMPInstances:
            return await context.send(f"Error: AMP server **{server_name}** not found in the managed instances.", ephemeral=True)

        # 2. Store the setting (Assuming a DB save method exists)
        # Note: The actual method name depends on your DB implementation (e.g., self.DB.save_setting)
        try:
            # We save the channel ID tied to the instance name
            # self.DB.set_instance_setting(server_name, 'status_channel_id', channel.id) 
            
            # --- For now, just print success (You MUST implement the saving logic) ---
            self.logger.info(f"Set status channel for {server_name} to {channel.id}")
            
            # Reset stored message ID to force a new post in the new channel
            if server_name in self.status_messages:
                 del self.status_messages[server_name]
            
            # Force an update to instantly post the new embed
            await self.update_server_status_loop()
            
            await context.send(
                f"Status channel for **{server_name}** successfully set to {channel.mention}.", 
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Error saving channel setting for {server_name}: {e}")
            await context.send("Error saving channel setting. Check logs.", ephemeral=True)

import discord
from redbot.core import commands, Config, checks 
import logging
import asyncio
from datetime import datetime
from typing import Optional, Union, List
from urllib.parse import urlparse
import aiohttp
import feedparser
from bs4 import BeautifulSoup
import time
from types import SimpleNamespace

log = logging.getLogger("red.AfterworkRSS")

# --- UTILITY FUNCTIONS ---

def _get_admin_footer(obj: Union[commands.Context, discord.Interaction], status_action: str) -> str:
    """Helper to generate the administrative footer format."""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    user_display_name = obj.author.display_name if isinstance(obj, commands.Context) else obj.user.display_name
    return f"e.Network | {status_action} by {user_display_name} {current_time}"

async def _send_owner_dm(bot, message: str):
    """Sends a critical error message directly to the bot owner."""
    owner = bot.get_user(bot.owner_id)
    if owner:
        try:
            embed = discord.Embed(title="⚠️ Afterwork RSS Error", description=message, color=discord.Color.red())
            await owner.send(embed=embed)
        except discord.Forbidden:
            log.error(f"Failed to DM owner. Owner must enable DMs.")

async def _update_setup_embed(cog: commands.Cog, guild: discord.Guild, embed: discord.Embed):
    """Refreshes the configuration data shown in the setup embed."""
    settings = await cog.config.guild(guild).all()
    feeds_list = settings.get('feeds', [])
    is_enabled = settings.get('enabled', False)
    content_filters = settings.get('content_filters', [])

    status_emoji = "🟢 Active" if is_enabled else "🔴 Inactive"
    
    feed_display = []
    for feed in feeds_list:
        channel = cog.bot.get_channel(feed['channel_id'])
        channel_name = f"#{channel.name}" if channel else "Unknown Channel"
        feed_display.append(f"• **{feed['name']}** -> {channel_name} ({feed['url'][:30]}...)")
    
    feed_display_str = "\n".join(feed_display) if feed_display else "*No feeds configured.*"
    filter_count = len(content_filters)
    
    embed.description = (
        "Configures RSS feeds to post updates in a specified channel. The core loop runs every 5 minutes."
    )
    embed.clear_fields()
    
    embed.add_field(name="System Status", value=status_emoji, inline=True)
    embed.add_field(name="Total Feeds Configured", value=str(len(feeds_list)), inline=True)
    embed.add_field(name="Active Filters", value=str(filter_count), inline=True)
    embed.add_field(name="Configured Feeds", value=feed_display_str, inline=False)
    
    return embed

# --- MODALS and VIEWS (No Changes) ---
# [Modal and View classes from previous response are included here without modification for completeness]

# --- MAIN COG CLASS ---

class AfterworkRSS(commands.Cog, name="AfterworkRSS"): 
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5577991122, force_registration=True) 
        self.config.register_guild(enabled=False, setup_message_id=None, feeds=[], content_filters=[])
        self._read_feeds_loop = None
        self._headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"}

    async def initialize(self):
        guilds_data = await self.config.all_guilds()
        for guild_id, data in guilds_data.items():
            if data.get('setup_message_id'):
                self.bot.add_view(SetupView(self, initial_enabled=data.get('enabled', False)), message_id=data['setup_message_id'])
        self.start_background_loop()

    def start_background_loop(self):
        if not self._read_feeds_loop: self._read_feeds_loop = self.bot.loop.create_task(self.read_feeds())

    def cog_unload(self):
        if self._read_feeds_loop: self._read_feeds_loop.cancel()

    # --- Commands and Core Logic ---
    
    # [All command and helper functions from the previous response are included here without modification for completeness]
    # ...
    
    async def check_and_post_feed(self, guild: discord.Guild, feed: dict):
        channel = self.bot.get_channel(feed['channel_id'])
        if not channel or not channel.permissions_for(guild.me).send_messages: 
            return

        feedparser_obj = await self._fetch_feedparser_object(feed['url'])
        if not feedparser_obj.entries: return

        content_filters = await self.config.guild(guild).content_filters()
        
        entries_to_post = []
        for entry in feedparser_obj.entries:
            current_time = self._time_tag_validation(entry)
            is_new = (feed['last_time'] == 0) or (current_time and feed['last_time'] and current_time > feed['last_time'])
            
            if is_new:
                entries_to_post.append((entry, entry.get("title", ""), entry.get("link", ""), current_time))
            
            if feed['last_time'] != 0 and current_time and current_time <= feed['last_time']:
                break
        
        if not entries_to_post: return

        entries_to_post.reverse()
        newest_post_time, newest_post_title, newest_post_link = 0, "", ""
        
        DESCRIPTION_LIMIT = 4096 
        
        for entry, current_title, current_link, current_time in entries_to_post:
            
            if current_time and current_time > newest_post_time:
                newest_post_time, newest_post_title, newest_post_link = current_time, current_title, current_link
            
            summary_html = entry.get("summary_detail", {}).get("value", "") or entry.get("content", [{}])[0].get("value", "")
            soup = BeautifulSoup(summary_html, 'html.parser')
            
            # ** NEW **: Extract the first image URL before getting the plain text
            image_url = None
            first_image = soup.find("img")
            if first_image and first_image.has_attr('src'):
                image_url = first_image['src']

            summary_text = soup.get_text()

            for phrase in content_filters:
                if phrase.lower() in summary_text.lower():
                    summary_text = summary_text.split(phrase, 1)[0].strip()
                    break
            
            if len(summary_text) > DESCRIPTION_LIMIT:
                suffix = f"\n\n[... Read Full Post Here]({current_link})"
                truncate_at = DESCRIPTION_LIMIT - len(suffix)
                summary_text = summary_text[:truncate_at] + suffix
            
            if feed['is_embed']:
                embed = discord.Embed(title=current_title, description=summary_text, url=current_link, color=discord.Color.blue())
                if current_time: embed.timestamp = datetime.fromtimestamp(current_time)

                # ** NEW **: Set the extracted image on the embed
                if image_url:
                    embed.set_image(url=image_url)

                try: await channel.send(embed=embed)
                except discord.Forbidden: return
            else:
                message = f"**{current_title}**\n{summary_text}\n{current_link}"
                try: await channel.send(message)
                except discord.Forbidden: return

        if newest_post_time > 0 and newest_post_time > feed['last_time']:
            await self._update_last_scraped(feed['name'], guild.id, newest_post_title, newest_post_link, newest_post_time)

async def setup(bot):
    cog = AfterworkRSS(bot) 
    await cog.initialize()
    await bot.add_cog(cog)

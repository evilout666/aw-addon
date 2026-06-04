# Red-DiscordBot API Integration

If you want to control your Red-DiscordBot cogs directly from an external dashboard like `dash.afterworkplay.com`, you have a few architectural choices. Red-DiscordBot does not have a native, built-in REST API enabled by default. However, because it is built on `discord.py` and Python `asyncio`, you can easily expose an HTTP API from within your own custom cogs!

## Approach 1: Embedded `aiohttp` Web Server in a Custom Cog (Recommended)

Since Red-DiscordBot already runs inside an asynchronous event loop and uses the `aiohttp` library for web requests, the most efficient and robust method is to spin up a lightweight `aiohttp.web` server directly inside your custom cog. 

This allows your external dashboard to send HTTP POST requests directly to the bot, which can then use `self.bot` to immediately execute Discord actions (like sending an embed to a channel).

### Example Implementation

```python
import aiohttp.web
from redbot.core import commands
import asyncio

class DashboardAPI(commands.Cog):
    """Cog that exposes a local HTTP API for dash.afterworkplay.com"""

    def __init__(self, bot):
        self.bot = bot
        self.app = aiohttp.web.Application()
        self.runner = None
        self.site = None
        
        # Setup API Routes
        self.app.router.add_post('/api/post_news', self.handle_post_news)
        
        # Start the web server in the background
        self.bot.loop.create_task(self.start_server())

    async def start_server(self):
        self.runner = aiohttp.web.AppRunner(self.app)
        await self.runner.setup()
        # Bind to localhost (or 0.0.0.0 if behind a reverse proxy) on an unused port
        self.site = aiohttp.web.TCPSite(self.runner, '127.0.0.1', 8080)
        await self.site.start()
        print("Dashboard API started on http://127.0.0.1:8080")

    def cog_unload(self):
        """Cleanup when the cog is unloaded"""
        if self.runner:
            self.bot.loop.create_task(self.runner.cleanup())

    # --- Route Handlers ---
    
    async def handle_post_news(self, request):
        """Endpoint to receive POST requests from dash.afterworkplay.com"""
        # Validate security token/API key here!
        auth = request.headers.get('Authorization')
        if auth != "Bearer YOUR_SECRET_API_KEY":
            return aiohttp.web.json_response({"error": "Unauthorized"}, status=401)
            
        try:
            data = await request.json()
            channel_id = data.get('channel_id')
            title = data.get('title')
            content = data.get('content')
            
            # Use Redbot's bot instance to send the message
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await channel.send(f"**{title}**\n{content}")
                return aiohttp.web.json_response({"status": "success", "message": "News posted!"})
            else:
                return aiohttp.web.json_response({"error": "Channel not found"}, status=404)
                
        except Exception as e:
            return aiohttp.web.json_response({"error": str(e)}, status=500)
```

### Security Considerations for Approach 1:
- **Authentication**: You MUST enforce a secret API key or JWT token system in your route handlers (as shown above) to ensure that only `dash.afterworkplay.com` can trigger Discord posts.
- **Networking**: Run this server on `127.0.0.1` and use a reverse proxy (like Nginx or Cloudflare Tunnels) to expose it to the internet safely with HTTPS.

## Approach 2: Red-Web-Dashboard (RPC Method)

There is a community project called `Red-Web-Dashboard` which attempts to provide a generic web interface for Redbot. It uses an RPC (Remote Procedure Call) mechanism to talk to the bot.
- **Pros**: Established standard for some community cogs.
- **Cons**: Extremely heavy, often suffers from version incompatibility with newer Redbot releases, requires setting up complex isolated Python environments, and gives you less custom control over the API structure compared to writing your own endpoint.

### Conclusion
For `AfterworkPlay`, where you just want a "control manager" to directly trigger posts from your own custom Dashboard to Discord, **Approach 1 (Embedded `aiohttp` web server)** is drastically superior. It gives you 100% control over the JSON schema, allows you to trigger precise Discord actions securely, and lives directly inside your `afterwork` cog ecosystem without relying on fragile third-party dashboard systems.

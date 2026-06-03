# Afterwork AWCogs — AI Assistant Rules

This repository contains the official Discord Bot cog for the Afterwork Play server management. 

---

## 🚀 Branch Strategy (3-Branch Reorganization)

The project is split into three dedicated branches. Ensure you are committing code to the correct branch based on your modifications:

| Branch | Description | Tech Stack | Root Files |
| --- | --- | --- | --- |
| **`main`** | Discord bot cog only | Python (Red-DiscordBot, discord.py) | `afterwork/`, `README.md`, `AGY.md` |
| **`backend`** | Go status bridge service | Go (CubeCoders AMP status client) | `main.go`, `install.sh`, `README.md` |
| **`dashboard`** | Static Web Admin UI | Vanilla HTML, CSS, JavaScript | `index.html`, `app.js`, `style.css` |

---

## 🐍 Python / Cog Coding Guidelines (`main` branch)

The main cog is located in **[afterwork/](file:///root/projects/redbot-cogs/AWCogs/afterwork)** and is written as a unified cog class `Afterwork` under `redbot.core.commands`.

### 🛡️ Owner-Only Security
* All configuration commands, panels, and interactive elements are **strictly owner-only** for safety.
* Commands must be annotated with `@commands.is_owner()`.
* Every interaction callback (in Buttons, Selects, Modals) must verify the user's owner status:
  ```python
  if not await self.cog.bot.is_owner(interaction.user):
      await interaction.response.send_message("You are not authorized to use this.", ephemeral=True)
      return
  ```

### 🎨 Interaction UX Pattern
* **"Public Error, Ephemeral Success"**
  * When an action succeeds, acknowledge it privately (set `ephemeral=True` or `interaction.response.defer(ephemeral=True)`) or delete the notification after a few seconds to avoid cluttering the channel.
  * When a command fails or invalid input is provided, log it and send a descriptive alert (e.g. to the bot owner's DM).

### 🏷️ Namespace Prefixing
To prevent namespace collisions within the single unified cog class:
1. **Config Key Namespace:** Prefix all configuration parameters in `Config.register_guild` with the subsystem name (e.g., `audio_music_voice_channel_id`, `rss_feeds`, `tv_enabled`).
2. **Views & Modals:** Always prefix classes:
   * **Audio:** `AudioSetVoiceChannelModal`, `AudioAddPlaylistModal`
   * **Embed:** `EmbedSendModal`, `EmbedSetupView`
3. **Helper Methods:** Prefix internal functions with an underscore and the subsystem name (e.g., `_update_audio_setup_embed()`, `_send_owner_dm()`).

### ⚠️ Error Handling & Logging
* Log standard exceptions to the cog logger: `log = logging.getLogger("red.Afterwork")`.
* Use the helper `_send_owner_dm(self.bot, message)` to notify the bot owner directly of critical error events or incorrect settings configurations.

---

## ⚙️ Go Backend Guidelines (`backend` branch)
* **Design Philosophy:** Minimal dependency Go HTTP service.
* **Standards:** Respect caching headers, handle timeouts gracefully, and return proper HTTP status codes.
* **CORS:** Ensure strict CORS matching for the authorized Afterwork dashboard origin.

---

## 💻 Web Dashboard Guidelines (`dashboard` branch)
* **Tech Stack:** Vanilla HTML/JS/CSS.
* **Aesthetics:** High-end premium dark mode theme, using modern fonts, responsive grids, and clean visual indicators.
* **Deployment:** Pushes to the `dashboard` branch trigger a GitHub Action that deploys directly to Cloudflare Pages.

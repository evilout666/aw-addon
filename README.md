# Afterwork Cog (AWCogs)

A unified, standalone administration and automation cog for Red-DiscordBot, specifically tailored for private game server community management.

---

## 🎨 Design Philosophy

The cog adheres to a clean, standardized user experience and security model:

* **Owner-Only Security:** All configuration commands, deployment panels, and button interactions are restricted to the bot owner to maintain maximum server control and security.
* **Interactive Control Hubs:** Rather than complex slash commands, each module is managed via a single, persistent, pinned message (a "hub") containing interactive Discord components.
* **Modern UI Components:** Actions (locking rooms, adding RSS feeds, playing music) are triggered via Select Menus, Buttons, and Modals.
* **Clean Channel UX:** Implements a strict *"Public Error, Ephemeral Success"* policy. Error notifications are posted publicly for immediate visibility, whereas success messages are sent ephemerally to keep admin channels tidy.

---

## 📦 Subsystems

The unified cog merges 6 distinct administrative sub-modules into one cohesive package:

| Subsystem | Core Feature | Discord UI Components |
|:---|:---|:---|
| **Audio** | Pinned controls for Red's official Audio cog | Interactive play/pause, skip, volume slider, and custom playlist selector. |
| **Embed** | Secure custom JSON message publisher | Interactive JSON validator modal to send custom embeds to saved channels. |
| **RSS** | Multi-feed background polling engine | Subscription control panel to add, remove, and route feeds every 5 minutes. |
| **TV Webhooks** | Refined Sonarr/Radarr announcement feed | Formats raw webhook payloads into sleek announcements with metadata. |
| **Voice** | Temporary AutoRoom controller | Allows room owners to Lock, Hide, Kick, or Transfer ownership via a panel. |
| **Hide** | Category-wide visibility administrator | Toggles server category access for admins or moderators with a single button. |

---

## 🛠️ Deployment Commands

Deploy the hubs in a designated administration channel using the following command structure:

| Command | Action |
|:---|:---|
| `[p]afterwork` | Displays the status dashboard showing active/inactive modules. |
| `[p]afterwork help` | Lists all available subcommand groups. |
| `[p]afterwork deploy` | Deploys all 6 interactive configuration hubs sequentially. |
| `[p]afterwork deploy audio` | Deploys the Audio player control settings hub. |
| `[p]afterwork deploy embed` | Deploys the custom JSON embed publisher hub. |
| `[p]afterwork deploy rss` | Deploys the RSS feed subscription hub. |
| `[p]afterwork deploy tv` | Deploys the Sonarr/Radarr webhook filter hub. |
| `[p]afterwork deploy voice` | Deploys the temporary voice room management hub. |
| `[p]afterwork deploy hide` | Deploys the category visibility toggle hub. |

---

## 🚀 Installation & Setup

### 1. Placement
Copy the **[afterwork/](file:///root/projects/redbot-cogs/AWCogs/afterwork)** folder into a valid cog directory on your Red-DiscordBot instance (use `[p]paths` to list valid paths).

### 2. Loading
Load the cog on your Discord instance:
```discord
[p]load afterwork
```

### 3. Deploying Hubs
Create a private channel for administrator controls and run:
```discord
[p]afterwork deploy
```

---

## 📂 Project Organization

This repository uses a multi-branch layout to isolate the Discord Bot Cog, the Go Status Service, and the static web Dashboard:

* **[afterwork/](file:///root/projects/redbot-cogs/AWCogs/afterwork)** (Python): The Discord bot cog files (located on this **`main`** branch).
* **[AGY.md](file:///root/projects/redbot-cogs/AWCogs/AGY.md)**: AI assistant coding standards and branch directory definitions.
* **[STATUS.md](file:///root/projects/redbot-cogs/AWCogs/STATUS.md)**: Feature logs and future ideas status board.
* **`backend` Branch** (Go): Contains the Go server status bridge.
* **`dashboard` Branch** (Static HTML/JS): Contains the web control dashboard.

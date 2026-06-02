# AfterWork Cog for Red-DiscordBot

This repository contains a unified, standalone cog for Red-DiscordBot designed for private server administration. The cog integrates multiple automation hubs into a single control center managed through persistent interactive control panels.

## Design Philosophy

The cog follows a consistent design pattern:
- **Owner-Only:** All configuration commands, panels, and interactions are restricted to the bot owner for maximum security.
- **Interactive Hubs:** Each module is managed via a single, persistent, pinned message (a "hub") deployed via a simple command.
- **Modern UI:** Configuration and actions are handled through Discord Components like Select Menus, Buttons, and Modals (pop-up forms), not complex text commands.
- **Clean UX:** The system uses a "Public Error, Ephemeral Success" policy. Error notifications are posted publicly for immediate visibility, while successful actions are acknowledged privately and temporarily to keep channels clean.

## Unified Features

The unified **Afterwork** cog combines the following features into one command group:

- **Audio:** A persistent player control panel for Red's official Audio cog, allowing users to request songs/playlists, pause, skip, and stop via buttons.
- **Embed:** A secure utility to send custom, complex embed messages from JSON payloads to configured channels.
- **RSS:** A background reader that polls RSS/Atom feeds, validates updates, filters content, and posts summaries with extracted images.
- **TV:** Intercepts webhook embeds from Sonarr and Radarr, reformats them cleanly, and reposts them to a news feed.
- **Voice:** Manages control panels for temporary voice channels created by an external AutoRoom cog, granting room owners control over lock/unlock, privacy, kick, and ownership transfer.
- **Hide:** Standardized category visibility management, hiding/showing Category channels from roles with Administrator or Manage Channels permissions.

## Deploy Commands

Deploy the hubs in a channel using the following command structure:

| Command | Action |
| --- | --- |
| `[p]afterwork` | Deploys/redeploys all 6 configuration hubs sequentially. |
| `[p]afterwork audio` | Deploys the Audio player control settings hub. |
| `[p]afterwork embed` | Deploys the custom JSON embed sender hub. |
| `[p]afterwork rss` | Deploys the RSS feed configuration hub. |
| `[p]afterwork tv` | Deploys the Sonarr and Radarr webhook reformatter hub. |
| `[p]afterwork voice` | Deploys the temporary voice room management hub. |
| `[p]afterwork hide` | Deploys the category visibility hide/show hub. |
| `[p]afterwork rss remove <name>` | Removes an RSS feed configuration by its unique name. |

## Installation and Usage

1. **Placement:** Place the `afterwork` folder into a valid cog path for your Red-DiscordBot instance (check paths with `[p]paths`).
2. **Loading:** Load the unified cog using:
   ```
   [p]load afterwork
   ```
3. **Setup:** Run `[p]afterwork` in your designated admin channel to deploy all persistent control hubs at once, or use the subcommands to deploy specific ones.

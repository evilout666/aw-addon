# AI Assistant Rules

Custom Discord RedBot cog for server: AFTERWORK Play 

# Official guide for making cogs

https://docs.discord.red/en/stable/guide_cog_creation.html

# Functions

command: [p]afterwork
action: should open/give link for https://dash.afterworkplay.com

command:  [p]afterwork help
action: list all subcommands

# 🌌 Antigravity CLI (AGY) - System Blueprint

This file serves as the core blueprint for the Antigravity CLI environment. The `antigravity-bridge` Go agent parses this specification to monitor system assets, maintain project lifecycle states, and sync infrastructure nodes.

---

## 📊 AGY Project Tracking Matrix

Your Go CLI reads this block on execution initialization to evaluate project health and determine build workflows.

### 🟢 Completed Tasks
*   [x] Core `[p]afterwork` base command group fully implemented in RedBot cog.
*   [x] Configured direct hyperlink redirection frame pointing to `https://dash.afterworkplay.com`.
*   [x] Built dynamic internal help index parser to loop over registered subcommands.
*   [x] Implement `[p]afterwork deploy` root command group inside the Python module.
*   [x] Inject the custom JSON embed interpreter engine (`deploy embed`).
*   [x] Code the RSS configuration/removal pipeline hubs.
*   [x] Build the media webhook reformatting schemas (`deploy tv`).
*   [x] Establish temporary voice room and category hide parameters (`voice` / `hide`).

### 🟡 Pending Tasks (AGY Worklist)
*   [ ] Monitor system logs and gather user feedback for potential performance optimizations.

---

## 🛠️ Installation & Architecture

The system is deployed via a unified bash script. The installer compiles the Go background daemon, establishes system security context, and mounts the systemd service.

### 📋 Installation Hook (`install.sh`)

```bash
#!/usr/bin/env bash
# Antigravity CLI - Core Daemon Installer
set -e

echo "🚀 [Antigravity] Initiating deployment pipeline..."

# 1. Compile the high-performance Go binary
if [ -d "./cmd/bridge" ]; then
    echo "📦 Compiling Antigravity Status Bridge..."
    go build -ldflags="-s -w" -o /usr/local/bin/antigravity-bridge ./cmd/bridge
else
    echo "❌ Error: Go source tree not found at ./cmd/bridge" && exit 1
fi

# 2. Establish persistent Configuration space
mkdir -p /etc/antigravity

# 3. Provision Systemd service unit
echo "⚙️ Configuring systemd service layer..."
cat << 'EOF' > /etc/systemd/system/antigravity-bridge.service
[Unit]
Description=Antigravity Core Status Daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/antigravity-bridge --blueprint /opt/antigravity/agy.md
Restart=always
RestartSec=5
User=amp
Group=amp
WorkingDirectory=/opt/antigravity

[Install]
WantedBy=multi-user.target
EOF

# 4. Reload and activate daemon
systemctl daemon-reload
systemctl enable --now antigravity-bridge
echo "✅ [Antigravity] Service initialized and running background cycles."
```

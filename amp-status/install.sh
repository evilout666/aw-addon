#!/usr/bin/env bash
set -e

# Ensure running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Error: Please run this installer as root (sudo)."
    exit 1
fi

echo "🚀 [Antigravity-AMP] Starting installation..."

# Detect Go compiler
if ! command -v go &> /dev/null; then
    echo "📦 Go compiler not found. Attempting to install golang..."
    if command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y golang
    else
        echo "❌ Error: Package manager 'apt-get' not found. Please install Go manually before running this script."
        exit 1
    fi
fi

# Build Go binary
echo "📦 Building AMP Status Bridge Go service..."
cd "$(dirname "$0")"
go build -ldflags="-s -w" -o /usr/local/bin/antigravity-amp main.go
echo "✅ Build completed: /usr/local/bin/antigravity-amp"

# Create config directory
mkdir -p /etc/antigravity-amp

# Deploy config file if not already present
if [ ! -f /etc/antigravity-amp/config.json ]; then
    echo "⚙️ Creating configuration at /etc/antigravity-amp/config.json..."
    cp config.json.example /etc/antigravity-amp/config.json
    echo "⚠️ NOTE: Please edit /etc/antigravity-amp/config.json with your AMP credentials!"
else
    echo "ℹ️ Existing configuration found at /etc/antigravity-amp/config.json. Skipping overwrite."
fi

# Determine service User and Group
SERVICE_USER="root"
SERVICE_GROUP="root"
if id "amp" &>/dev/null; then
    echo "👤 User 'amp' detected. Configuring service to run as 'amp' user."
    SERVICE_USER="amp"
    SERVICE_GROUP="amp"
    # Ensure config file is owned and readable by amp user
    chown -R amp:amp /etc/antigravity-amp
else
    echo "👤 User 'amp' not found. Running service as 'root'."
fi

# Write Systemd service file
echo "⚙️ Installing systemd service..."
cat << EOF > /etc/systemd/system/antigravity-amp.service
[Unit]
Description=Antigravity AMP Server Status Bridge
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/antigravity-amp --config /etc/antigravity-amp/config.json
Restart=always
RestartSec=5
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=/etc/antigravity-amp

[Install]
WantedBy=multi-user.target
EOF

# Reload and restart service
systemctl daemon-reload
systemctl enable antigravity-amp
systemctl restart antigravity-amp || echo "⚠️ Service registered but failed to start. (Ensure configuration has valid URL and credentials)"

echo "✅ [Antigravity-AMP] Installation complete!"
echo "✨ The service is registered with systemd as 'antigravity-amp'."
echo "💡 To configure: nano /etc/antigravity-amp/config.json"
echo "💡 To start:     systemctl start antigravity-amp"
echo "💡 To view logs: journalctl -u antigravity-amp -f"

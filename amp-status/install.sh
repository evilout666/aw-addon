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

# Simple function to extract JSON field value (perl-compatible regex)
get_json_val() {
    local file="$1"
    local key="$2"
    local default="$3"
    if [ -f "$file" ]; then
        local val=$(grep -Po '"'"$key"'"\s*:\s*"\K[^"]*' "$file" 2>/dev/null || grep -Po '"'"$key"'"\s*:\s*\K[0-9]*' "$file" 2>/dev/null || echo "")
        echo "${val:-$default}"
    else
        echo "$default"
    fi
}

# --- Configuration Wizard ---
echo ""
echo "⚙️  Configuring AMP Status Bridge..."
CONFIG_FILE="/etc/antigravity-amp/config.json"

# Load existing values or defaults from config.json or config.json.example
TEMPLATE_FILE="config.json.example"
if [ -f "$CONFIG_FILE" ]; then
    BASE_FILE="$CONFIG_FILE"
else
    BASE_FILE="$TEMPLATE_FILE"
fi

EXISTING_URL=$(get_json_val "$BASE_FILE" "amp_url" "http://localhost:8080")
EXISTING_USER=$(get_json_val "$BASE_FILE" "amp_username" "admin")
EXISTING_PASS=$(get_json_val "$BASE_FILE" "amp_password" "")
EXISTING_BIND=$(get_json_val "$BASE_FILE" "bind_address" "0.0.0.0:9876")
EXISTING_CACHE=$(get_json_val "$BASE_FILE" "cache_duration_seconds" "10")

# Ask questions with defaults
read -p "  AMP URL [$EXISTING_URL]: " input_url
AMP_URL="${input_url:-$EXISTING_URL}"

read -p "  AMP Username [$EXISTING_USER]: " input_user
AMP_USERNAME="${input_user:-$EXISTING_USER}"

# Prompt for password. If existing password exists, show default option to keep it
if [ -n "$EXISTING_PASS" ] && [ "$EXISTING_PASS" != "yourpasswordhere" ]; then
    read -p "  AMP Password [keep existing password]: " input_pass
    AMP_PASSWORD="${input_pass:-$EXISTING_PASS}"
else
    read -p "  AMP Password: " input_pass
    AMP_PASSWORD="$input_pass"
fi

read -p "  Bind Address [$EXISTING_BIND]: " input_bind
BIND_ADDRESS="${input_bind:-$EXISTING_BIND}"

read -p "  Cache Duration (seconds) [$EXISTING_CACHE]: " input_cache
CACHE_DURATION="${input_cache:-$EXISTING_CACHE}"

# Write config file
cat << EOF > "$CONFIG_FILE"
{
  "amp_url": "${AMP_URL}",
  "amp_username": "${AMP_USERNAME}",
  "amp_password": "${AMP_PASSWORD}",
  "bind_address": "${BIND_ADDRESS}",
  "cache_duration_seconds": ${CACHE_DURATION}
}
EOF
echo "✅ Configuration saved to $CONFIG_FILE"
echo ""

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

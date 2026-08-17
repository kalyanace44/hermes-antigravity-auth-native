#!/usr/bin/env bash
set -e

# ==============================================================================
# Hermes Google Antigravity Auth Plugin Installer (Native)
# ==============================================================================

HERMES_DIR="$HOME/.hermes"
HERMES_PLUGINS_DIR="$HERMES_DIR/plugins"
HERMES_PROVIDERS_DIR="$HERMES_PLUGINS_DIR/model-providers"
CONFIG_FILE="$HERMES_DIR/config.yaml"
ENV_FILE="$HERMES_DIR/.env"
AUTH_FILE="$HERMES_DIR/auth.json"

echo "📦 Installing Hermes Antigravity Auth Plugin..."

# Check if running locally or via curl stream
if [ ! -d "plugins/antigravity" ]; then
    echo "🌍 Downloading files from GitHub..."
    TEMP_DIR="/tmp/hermes-antigravity-auth-temp"
    rm -rf "$TEMP_DIR"
    mkdir -p "$TEMP_DIR"
    
    curl -fsSL https://github.com/kalyanace44/hermes-antigravity-auth-native/archive/refs/heads/main.zip -o "$TEMP_DIR/repo.zip"
    unzip -q "$TEMP_DIR/repo.zip" -d "$TEMP_DIR"
    
    SRC_PATH="$TEMP_DIR/hermes-antigravity-auth-native-main"
else
    SRC_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    TEMP_DIR=""
fi

# Create target directories
mkdir -p "$HERMES_PLUGINS_DIR/antigravity"
mkdir -p "$HERMES_PROVIDERS_DIR/antigravity"

# Copy plugin files
cp -rf "$SRC_PATH/plugins/antigravity/"* "$HERMES_PLUGINS_DIR/antigravity/"
cp -rf "$SRC_PATH/plugins/model-providers/antigravity/"* "$HERMES_PROVIDERS_DIR/antigravity/"

echo "⚙️ Configuring Hermes provider settings..."

# 1. Append antigravity provider to config.yaml if not present
if [ -f "$CONFIG_FILE" ]; then
    if ! grep -q "antigravity:" "$CONFIG_FILE"; then
        cat << 'EOF' >> "$CONFIG_FILE"

  antigravity:
    api_key: mock
    base_url: http://127.0.0.1:8999/v1
    default_model: gemini-3.7-flash
    models:
      - gemini-3.7-flash
      - claude-sonnet-4-6
      - claude-opus-4-6
      - claude-3-5-sonnet
      - claude-3-opus
      - gpt-oss-120b
      - gemini-3.1-pro
      - gemini-3-flash
      - gemini-2.5-flash
EOF
        echo "✅ Added Antigravity provider to ~/.hermes/config.yaml"
    fi
fi

# 2. Add credentials to ~/.hermes/.env
if [ -f "$ENV_FILE" ]; then
    if ! grep -q "ANTIGRAVITY_API_KEY" "$ENV_FILE"; then
        echo "" >> "$ENV_FILE"
        echo "ANTIGRAVITY_API_KEY=mock" >> "$ENV_FILE"
        echo "ANTIGRAVITY_BASE_URL=http://127.0.0.1:8999/v1" >> "$ENV_FILE"
        echo "✅ Added ANTIGRAVITY credentials to ~/.hermes/.env"
    fi
else
    echo "ANTIGRAVITY_API_KEY=mock" >> "$ENV_FILE"
    echo "ANTIGRAVITY_BASE_URL=http://127.0.0.1:8999/v1" >> "$ENV_FILE"
fi

# 3. Restart Antigravity proxy daemon
PID=$(lsof -t -i:8999 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "🔄 Refreshing Antigravity daemon..."
    kill -9 "$PID" 2>/dev/null || true
fi

# Clean up temp files if created
if [ -n "$TEMP_DIR" ]; then
    rm -rf "$TEMP_DIR"
fi

echo ""
echo "🎉 Installation complete!"
echo "👉 Reload Hermes (Cmd + R) to access Google Antigravity models in your model selector."

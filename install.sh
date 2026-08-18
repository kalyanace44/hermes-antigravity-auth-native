#!/bin/bash
set -e

REPO="kalyanace44/hermes-antigravity-auth-native"
HERMES_DIR="$HOME/.hermes"
PLUGINS_DIR="$HERMES_DIR/plugins"
PROVIDERS_DIR="$HERMES_DIR/plugins/model-providers"

echo "🔌 Installing Hermes Antigravity Auth Plugin..."

# Check if running from local clone or web pipe
if [ -f "plugins/antigravity/__init__.py" ]; then
    echo "   Local install detected."
    SOURCE_DIR="."
else
    echo "   Downloading from GitHub..."
    TMP_DIR=$(mktemp -d)
    curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.zip" -o "$TMP_DIR/repo.zip"
    unzip -q "$TMP_DIR/repo.zip" -d "$TMP_DIR"
    SOURCE_DIR="$TMP_DIR/hermes-antigravity-auth-native-main"
fi

# Deploy plugin
echo "   Deploying antigravity plugin..."
rm -rf "$PLUGINS_DIR/antigravity"
mkdir -p "$PLUGINS_DIR/antigravity"
cp "$SOURCE_DIR/plugins/antigravity/__init__.py" "$PLUGINS_DIR/antigravity/"
cp "$SOURCE_DIR/plugins/antigravity/plugin.yaml" "$PLUGINS_DIR/antigravity/"

# Deploy model provider
echo "   Deploying model provider..."
rm -rf "$PROVIDERS_DIR/antigravity"
mkdir -p "$PROVIDERS_DIR/antigravity"
cp "$SOURCE_DIR/plugins/model-providers/antigravity/__init__.py" "$PROVIDERS_DIR/antigravity/"
cp "$SOURCE_DIR/plugins/model-providers/antigravity/plugin.yaml" "$PROVIDERS_DIR/antigravity/"

# Cleanup temp
if [ -n "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
fi

# Check for existing accounts
if [ -f "$HERMES_DIR/antigravity-accounts.json" ]; then
    echo "   ✅ Existing account found."
else
    echo "   ⚠️  No accounts configured. Run /antigravity-login in Hermes chat after restart."
fi

echo ""
echo "✅ Hermes Antigravity Auth Plugin installed!"
echo "   Proxy port: 8999"
echo "   Accounts:   ~/.hermes/antigravity-accounts.json"
echo ""
echo "   Restart Hermes (Cmd+R) to activate the plugin."

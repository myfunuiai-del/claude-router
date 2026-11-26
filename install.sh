#!/usr/bin/env bash
# Claude Router (C-Router) One-Step Installer / Setup Script
set -e

ROUTER_DIR="$HOME/.gemini/claude-router"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Installing Claude Router to $ROUTER_DIR..."
mkdir -p "$ROUTER_DIR"

# If cloned elsewhere, copy project files into ~/.gemini/claude-router
if [ "$SCRIPT_DIR" != "$ROUTER_DIR" ]; then
    cp -a "$SCRIPT_DIR"/. "$ROUTER_DIR"/
fi

# Create default config.json from config.example.json if missing
if [ ! -f "$ROUTER_DIR/config.json" ] && [ -f "$ROUTER_DIR/config.example.json" ]; then
    cp "$ROUTER_DIR/config.example.json" "$ROUTER_DIR/config.json"
    echo "✅ Created initial config.json from config.example.json"
fi

chmod +x "$ROUTER_DIR/crouter" "$ROUTER_DIR/install.sh" 2>/dev/null || true

# Start router (automatically sets up symlinks, skills, and ~/.bashrc auto-start)
"$ROUTER_DIR/crouter" start

echo ""
echo "✅ Claude Router installed! Auto-Start on Launch is enabled by default."
echo "   • Toggle Auto-Start: crouter autostart on|off  (or in Dashboard Sidebar)"
echo "   • Uninstall anytime: crouter uninstall         (or Sidebar bottom button)"

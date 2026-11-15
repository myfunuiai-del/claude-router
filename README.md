# ⚡ Claude Router: Bulletproof Multi-Provider AI Gateway & Failover Proxy

A lightweight, zero-dependency local proxy gateway designed for **Claude Code**, **Antigravity**, **Aider**, and any AI CLI/IDE tool. 

It unifies multiple AI providers into a single high-availability Anthropic-compatible endpoint (`http://127.0.0.1:8999/api`), featuring automatic cascading failover, mobile-first web dashboard, dynamic key pooling, and protocol translation.

---

## ✨ Features

- **Multi-Server Provider Support:**
  - Anthropic native (`Coarena`, `AgentRouter`, `GonkaBroker`, `OpenRouter`).
  - OpenAI chat completion models (`Groq LPU`, etc.) with automatic Anthropic SSE stream and JSON conversion.
- **Dynamic Dual-Pool Architecture:**
  - **⚡ ROUTED PIPELINE (ACTIVE):** Automatic cascade in strict priority order (`#1 Primary` ➔ `#2 Fallback` ➔ `#3 Fallback`). If a server runs out of credits (`HTTP 402`), hits rate limits (`HTTP 429`), or goes offline, traffic cascades instantly to the next provider.
  - **💤 STANDBY / FREE POOL:** Inactive providers held in reserve.
- **User Selection Priority Override:**
  - If you select a specific model in your chat dropdown (e.g. `@groq/openai/gpt-oss-120b`, `@openrouter/baidu/ernie-5.5-flash-preview:free`, or `@gonkabroker/zai-org/GLM-5.3-Flash`), the router routes to that provider first. If it fails, it cascades gracefully to the pipeline.
- **Zero-Dependency Core:**
  - Built strictly using standard Python (`http.server`, `urllib.request`, `json`, `socket`). No `pip install` or heavyweight libraries required.
- **Safe Web UI & 10-Second Undo:**
  - Interactive Mobile & Desktop Web Console at `http://127.0.0.1:8999/ui`.
  - Drag-and-drop & 1-tap reordering (`▲`/`▼`) of priority pipeline.
  - Zero single-click deletions with 10-second animated undo bar.
  - One-click model ping and live status badges (`🟢`/`🔴`).
- **Terminal CLI & Auto-Start Guard:**
  - Comes with `crouter` CLI command (`crouter start`, `crouter stop`, `crouter status`).
  - Self-healing auto-start guard in `~/.bashrc`.

---

## 🚀 Quick Setup & Installation

### 1. Clone or Copy Files
Place the project files into `~/.gemini/claude-router`:
```bash
git clone https://github.com/your-username/claude-router.git ~/.gemini/claude-router
cd ~/.gemini/claude-router
```

### 2. Add `crouter` Management CLI
Create or symlink the helper script to your path:
```bash
mkdir -p ~/.local/bin
cat << 'EOF' > ~/.local/bin/crouter
#!/usr/bin/env bash
ROUTER_DIR="$HOME/.gemini/claude-router"
PROXY_SCRIPT="$ROUTER_DIR/proxy_v2.py"
PORT=8999

case "$1" in
    start)
        python3 "$PROXY_SCRIPT" "$PORT" > "$ROUTER_DIR/proxy_v2.log" 2>&1 &
        echo "[Claude Router] Started on port $PORT."
        ;;
    stop)
        pkill -f "proxy_v2.py $PORT" 2>/dev/null || true
        echo "[Claude Router] Stopped."
        ;;
    status)
        curl -s "http://127.0.0.1:$PORT/status" | python3 -m json.tool 2>/dev/null || echo "Router offline."
        ;;
    *)
        echo "Usage: crouter {start|stop|restart|status|ui}"
        ;;
esac
EOF
chmod +x ~/.local/bin/crouter
```

### 3. Start the Server
```bash
crouter start
```
Open the Web Console in your browser:  
👉 **`http://127.0.0.1:8999/ui`**

---

## 🔌 Connecting to Claude Code / AI CLIs

### Option A: Using Environment Variables (Universal for any CLI)
Export these in your terminal session or shell profile:
```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8999/api"
export ANTHROPIC_API_KEY="auto"
```

### Option B: Claude Code Configuration (`~/.claude/settings.json`)
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8999/api",
    "ANTHROPIC_AUTH_TOKEN": "auto",
    "ANTHROPIC_API_KEY": ""
  }
}
```

---

## ⚙️ Architecture & Modular Structure

Every module is cleanly scoped under **500 lines** for maintainability:

```text
~/.gemini/claude-router/
├── proxy_v2.py               # Server entry point & IPv4 socket resolution
├── proxy_v2.config-1.py      # Config manager & key storage
├── proxy_v2.forwarder-1.py   # Cascading pipeline failover & direct routing
├── proxy_v2.transform-1.py   # SSE streaming & OpenAI-to-Anthropic protocol converter
├── proxy_v2.http_handlers-1.py # Static file server & CORS headers
├── proxy_v2.ui_api-1.py      # Web console backend API & ping discovery
├── dashboard.html            # Web console HTML markup
├── dashboard.styles-1.css    # Responsive CSS & animations
├── dashboard.servers-1.js    # Card rendering & dynamic state sync
├── dashboard.drag-1.js       # Touch & mouse drag-drop reordering
├── dashboard.modals-1.js     # Confirm dialogs & 10s animated undo engine
└── config.json               # Dynamic settings & provider pools
```

---

## 🛠️ Management CLI Commands

```bash
crouter start    # Starts router on port 8999 in background
crouter stop     # Gracefully stops the running router
crouter restart  # Restarts proxy process
crouter status   # Displays live server status and active provider
crouter ui       # Prints web dashboard URL
```

---

## 🛡️ License
MIT License. Free to use, modify, and distribute.

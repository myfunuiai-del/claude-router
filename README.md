# ⚡ Claude Router: Multi-Provider AI Gateway & Failover Proxy

<p align="center">
  <img src="assets/claude-router-logo.jpg" alt="Claude Router Logo" width="650" style="border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.5);" />
</p>

A lightweight, **zero-dependency** local AI proxy gateway built for **Claude Code**, **Antigravity**, **Aider**, and any Anthropic/OpenAI-compatible CLI or IDE.

It unifies multiple AI providers and API keys behind one local endpoint (`http://127.0.0.1:8999/api`), with a mobile-first Web Console (`http://127.0.0.1:8999/ui`), per-server ON/OFF switching, automatic chat-dropdown sync, 5-stage firewall/payload recovery, smart key cooldowns, and live concurrent testers.

---

## ✨ Key Features & How Each One Works

### 1. ⚡ Dual-Pool Priority Routing & Failover
- **⚡ ROUTED PIPELINE (ACTIVE):** Requests try enabled servers strictly from top to bottom (`#1 PRIMARY` ➔ `#2 FALLBACK 1` ➔ `#3 FALLBACK 2` ...). If a server fails or runs out of quota, traffic automatically cascades to the next active server.
- **💤 STANDBY / FREE POOL:** Reserve servers kept out of the automatic failover chain. Standby servers are **never** silently used as a hidden fallback.
- **Direct Provider Routes (`/{provider_id}`):** Every server exposes its own direct route (e.g. `http://127.0.0.1:8999/coarena`). Tap the `📋 /provider` pill on any card to copy its direct URL.

### 2. 🟢 Per-Server `ON / OFF` Switch & Live Chat Dropdown Sync
- Every server card has a compact **`● ON` / `● OFF`** toggle button in its header.
- **When turned `OFF`:**
  - The server is strictly blocked in the proxy backend (skipped in direct routes, smart model routes, and the failover pipeline).
  - Its models are **immediately removed** from the chat box model selector (`~/.claude/agy_providers.json`).
- **When turned `ON`:**
  - Routing resumes immediately and its models **reappear** in the chat dropdown automatically.

### 3. 🛡️ 5-Stage Auto History-Recovery (`Recovery: ON / OFF`)
When a long chat hits an upstream firewall/WAF or payload-size block (**HTTP `400` / `403` / `413`**) — and the request contains trimmable history — the router recovers the chat **without forcing you to open a new chat** and **without mutating your original chat history**:

| Stage | What It Sends | Why It Helps |
| :--- | :--- | :--- |
| **Original** | Full untouched chat history | Normal path (zero overhead when no error occurs) |
| **Stage 1** | Full history + **untouched last message**, shrinking only **older large `tool_result` outputs** | Keeps 100% of your conversation context intact while removing giant old logs/HTML dumps |
| **Stage 2** | Last **6–8 messages** (starting from a clean `user` turn) | Drops older problematic messages while preserving recent context |
| **Stage 3** | **Last message only** (preserving valid `tool_use`/`tool_result` pair if mid-tool-call) | Recovers when a recent turn contains a blocked pattern |
| **Stage 4** | Full history + last message with **all large tool outputs & text blocks shrunk** | Recovers even when the latest message itself contains a huge tool output |
| **Stage 5** | **Untouched original full request** routed to the **next `ON` server** in the pipeline | Seamless failover to another provider if the current server refuses all stages |

> - Recovery **never** triggers on `401` (bad key), `404` (invalid model), or `429` (rate limit).
> - You can toggle this feature anytime using the **`● Recovery: ON / OFF`** switch in the Live Status Bar.

### 4. ❄️ Smart API Key Auto-Cooldown
Avoids wasting time retrying dead or rate-limited keys on every single request:
- **`HTTP 401` (Invalid / Revoked Key):** Key is placed on a **10-minute** cooldown across all models.
- **`HTTP 429` (Rate Limit):** Key is placed on a **3-minute** cooldown across all models.
- **`HTTP 402` (Payment Required / Paid Model):** Only that specific **`(key + model)`** pair is placed on a **5-minute** cooldown — so the same key continues working normally for your free models.
- **Safe Fallback & Auto-Clear:** If *all* keys for a provider are in cooldown, the router still tries them so the provider never hard-locks. Any `200 OK` response or passing manual `Test` clears cooldown immediately.

### 5. 🧪 Live Concurrent Testers (60s Timeout, Progressive Updates)
- **API Keys Tester (`KEYS` ➔ `Test`):** Tests every key on a server in parallel (up to 60s timeout each). Whichever key responds first immediately displays `🟢 200 OK (ms)` or `🔴 401/402/...` right next to that key along with a live summary (`X/Y keys active`).
- **Models Compatibility Tester (`MODELS` ➔ `Select`):**
  - Discovers available models from the provider and automatically checks whether they work with your current API keys & settings.
  - Shows live status pills (`🟢 963ms`, `🔴 402`, `🔴 404`, etc.) next to every model before you add it.
  - Tap **`🟢 Only`** to filter the list down to working models only, **`Test All`** to test all visible/filtered models, or tap any individual model's status pill to test/re-test just that model.

### 6. 📡 `Console | Live Monitor` Switch Tab, Logs & Backup
- **`Console | Live Monitor` Tabs:** Switch between settings (`Console`) and real-time observability (`Live Monitor`) in one tap:
  - **⚡ Now Active (In-Flight):** Shows live requests currently being processed (server, model, key `#N`, stage, elapsed seconds).
  - **📊 Live Server Usage:** Per-server `OK / Fail` counts, success rate bar, average latency (`ms`), recoveries, and last error.
  - **🚨 Live Issues & Cooldowns:** Real-time error list with clear root-cause explanations (`401` invalid key, `402` paid model/no credit, `429` rate limit, `403` firewall block, `400/413` oversized history, timeouts), active cooldown countdowns, and 1-tap `Clear Cooldowns`.
  - **📡 Live Request Feed:** Reverse-chronological stream showing **which stage of the 5-stage Recovery / Failover passed** and **which server, model & key passed it** (`✅ Passed by: ...`).
- **`Logs` Button (Header):** Opens a live log viewer showing the latest 80 proxy log lines with **`Hide /status`** noise filter, **3-second Auto-Refresh**, and active **Cooldown count**.
- **`Backup` Button (Header):**
  - **Export JSON:** Download a dated config backup (`claude-router-backup-YYYY-MM-DD.json`), with an optional **"Include API Keys"** checkbox.
  - **Restore JSON:** Upload a `.json` file or paste JSON to restore servers & settings. Automatically saves your previous config to `config.json.bak` first and re-syncs `~/.claude/agy_providers.json`.

---

## 🎛️ Dashboard UI Quick Reference

| Control / Button | Location | What It Does |
| :--- | :--- | :--- |
| **`Logs`** | Top Header | Opens Live Proxy Logs modal (last 80 lines, `/status` filter, 3s auto-refresh, cooldown count) |
| **`Backup`** | Top Header | Opens Backup & Restore modal (Export JSON / Import JSON with auto `.bak` safety) |
| **`+ New Server`** | Top Header | Adds a new Anthropic or OpenAI-compatible provider server |
| **`● Recovery: ON/OFF`** | Live Status Bar | Enables or disables the 5-stage Auto History-Recovery system |
| **`Sync`** | Live Status Bar | Refreshes the active route, model, and account status immediately |
| **`+ Add Key`** | Quick Key Panel | Adds a new API key to the selected provider's key pool |
| **`● ON` / `● OFF`** | Each Server Card | Hard enables/disables the server in both routing and the chat model dropdown |
| **`⠿` / `▲` / `▼`** | Each Server Card | Drag-and-drop or 1-tap reorder failover priority |
| **`💤 Standby` / `⚡ Route`** | Each Server Card | Moves server between Active Routed Pipeline and Standby Pool |
| **`📋 /server_id`** | Each Server Card | Copies the dedicated direct route URL (`http://127.0.0.1:8999/<id>`) |
| **`✏️ Edit` / `🗑️`** | Each Server Card | Edits server settings or safely deletes with a 10-second Undo countdown bar |
| **`Select` / `Ping`** | Inside Card (`MODELS`) | Opens model discovery + compatibility tester modal / pings added models |
| **`🟢 Only` / `Test All`** | Inside `MODELS` Modal | Filters to working (`🟢`) models only / runs progressive compatibility check on visible models |
| **`Test`** | Inside Card (`KEYS`) | Concurrently tests all API keys on that server (60s timeout, fastest result shown first) |

---

## 🚀 Quick Setup & Installation

### 1. Clone & Create Config
```bash
git clone https://github.com/myfunuiai-del/claude-router.git ~/.gemini/claude-router
cd ~/.gemini/claude-router
cp config.example.json config.json
```

### 2. Symlink the `crouter` / `croute` CLI
```bash
mkdir -p ~/.local/bin
chmod +x ~/.gemini/claude-router/crouter
ln -sf ~/.gemini/claude-router/crouter ~/.local/bin/crouter
ln -sf ~/.local/bin/crouter ~/.local/bin/croute
```

### 3. Launch Router & Open Web Console
```bash
crouter
```
This starts the proxy on port `8999` (if offline) and automatically opens **`http://127.0.0.1:8999/ui`** in the foreground in-app browser (or Termux/system browser).

---

## 🛠️ Management CLI Commands

`crouter` and `croute` work identically:

```bash
crouter          # Starts proxy if offline, shows status, and opens Web UI in foreground
crouter start    # Starts proxy in background (and opens Web UI when run interactively)
crouter stop     # Stops the running proxy cleanly
crouter restart  # Restarts the proxy process
crouter status   # Displays running status and active provider/model JSON
crouter ui       # Opens http://127.0.0.1:8999/ui in the foreground browser
```

---

## 🔌 Connecting to Claude Code / AI CLIs

### Option A: Auto-Failover Pipeline (Recommended)
```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8999/api"
export ANTHROPIC_API_KEY="auto"
```

### Option B: Direct Single-Provider Route
```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8999/coarena"
export ANTHROPIC_API_KEY="auto"
```

### Option C: Claude Code Settings (`~/.claude/settings.json`)
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8999/api",
    "ANTHROPIC_AUTH_TOKEN": "auto",
    "ANTHROPIC_API_KEY": ""
  }
}
```
> **Auto Dropdown Sync:** Whenever you add, edit, reorder, or toggle a server `ON`/`OFF` in the Web Console, `~/.claude/agy_providers.json` is atomically updated in real time so your chat model dropdown always reflects only your enabled servers.

---

## ⚙️ Architecture, Files & Endpoints

### Modular File Map
```text
~/.gemini/claude-router/
├── crouter                     # CLI tool (start/stop/restart/status/ui + foreground browser launcher)
├── proxy_v2.py                 # Threaded HTTP server entry point (port 8999)
├── proxy_v2.config-1.py        # Config persistence, agy_providers.json sync, IPv4 fix, shared key cooldown store
├── proxy_v2.forwarder-1.py     # ON/OFF enforcement, key cooldown skipping, 5-stage recovery, pipeline failover
├── proxy_v2.transform-1.py     # OpenAI-to-Anthropic SSE/JSON converter, response tags, non-mutating history trimmers
├── proxy_v2.http_handlers-1.py # Static dashboard serving, /status, /api/ui/config, /api/ui/logs, DELETE handlers
├── proxy_v2.ui_api-1.py        # UI POST APIs: providers, keys, toggle, test-models, test-key, settings, config-import
├── dashboard.html              # Mobile-first Web Console markup & modals (Server, Models, Logs, Backup, Confirm)
├── dashboard.styles-1.css      # Responsive dark theme, clear list borders, power pills & log viewer styles
├── dashboard.servers-1.js      # Server cards, ON/OFF toggle, Recovery toggle, key provisioning
├── dashboard.drag-1.js         # Touch & mouse drag-and-drop priority reordering
├── dashboard.modals-1.js       # Model discovery/tester, key tester, Logs modal, Backup/Restore, 10s Undo engine
├── dashboard.live-1.js         # Console | Live tab switcher & real-time telemetry/issues/recovery feed UI
├── config.example.json         # Safe template config (tracked in Git)
└── config.json                 # Local live config with your real API keys (ignored by Git)
```

### Local HTTP API Reference
- `GET /ui` — Web Console dashboard
- `GET /status` — Active server, model, account, and last update timestamp
- `GET /api/ui/config` — Current full router configuration
- `GET /api/ui/logs?lines=80&hide_status=1` — Tail of `proxy_v2.log` + active key cooldowns
- `GET /api/ui/live` — Live Monitor snapshot (in-flight requests, per-server stats, issues with root cause, request feed with recovery stage & winner, active cooldowns)
- `POST /api/ui/live-action` — Clear active cooldowns or live telemetry (`clear_cooldowns`, `clear_issues`, `clear_all`)
- `POST /api/ui/providers` / `DELETE /api/ui/providers` — Create, edit, or delete a provider
- `POST /api/ui/provider-toggle` — Toggle a provider `ON` / `OFF` (`enabled: true | false`)
- `POST /api/ui/route-pool` — Update Active Pipeline order & Standby pool
- `POST /api/ui/keys` / `DELETE /api/ui/keys` — Add or revoke API keys
- `POST /api/ui/test-key` — Test a single API key (60s timeout) and clear its cooldown on `200 OK`
- `POST /api/ui/test-models` — Discover provider models and/or test model compatibility (60s timeout)
- `POST /api/ui/provider-models` — Add, remove, or set default model on a provider
- `POST /api/ui/settings` — Update global settings (`auto_recovery: true | false`)
- `POST /api/ui/config-import` — Safely restore config JSON (saves `config.json.bak` first)

---

## 🛡️ Security & Privacy Notes
- `config.json`, `config.json.bak`, `*backup*.json`, and `*.log` are excluded in `.gitignore` so real API keys and logs are never pushed to GitHub.
- Keep any exported backup file containing API keys private on your local device.

---

## 📄 License
MIT License. Free to use, modify, and distribute.

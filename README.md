# ⚡ Claude Router: Multi-Provider AI Gateway & Failover Proxy

<p align="center">
  <img src="assets/claude-router-logo.jpg" alt="Claude Router Logo" width="650" style="border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.5);" />
</p>

A lightweight, **zero-dependency** local AI proxy gateway built for **Claude Code**, **Antigravity**, **Aider**, and any Anthropic/OpenAI-compatible CLI or IDE.

It unifies multiple AI providers and API keys behind one local endpoint (`http://127.0.0.1:8999/api`), with a mobile-first Web Console (`http://127.0.0.1:8999/ui`), per-server ON/OFF switching, automatic chat-dropdown sync, 5-stage firewall/payload recovery, smart key cooldowns, and live concurrent testers.

---

## ✨ Key Features & How Each One Works

### 1. ⚡ Dual-Pool Priority Routing, Isolation & Intra-Server Multi-Model Fallback
- **⚡ ROUTED PIPELINE (ACTIVE):** Requests try enabled servers strictly from top to bottom (`#1 PRIMARY` ➔ `#2 FALLBACK 1` ➔ `#3 FALLBACK 2` ...). Before failing over to the next priority server, each server sequentially tries **all of its configured models** so healthy models on your primary server are exhausted first.
- **💤 STANDBY / FREE POOL (Strict Isolation):** Reserve servers kept out of the automatic failover chain. Dedicated requests sent to a standby route (e.g. `http://127.0.0.1:8999/googlestudio`) stay **strictly isolated** within that server — sequentially trying all of that server's models without ever cascading into the active routed pipeline.
- **Direct Provider Routes (`/{provider_id}`):** Every server exposes its own direct route (e.g. `http://127.0.0.1:8999/coarena`). Tap the `📋 /provider` pill on any card to copy its direct URL.

### 2. 🤖 Multi-Agent Architecture Mode (Preset Teams & Chat Dropdown Sync)
- **Custom Mix Teams (Role-Based Orchestra):** Build teams consisting of multiple servers and specific models (e.g., `Architect: Coarena gemini-4-carbon` + `Coder: Groq gpt-oss-120b`).
- **Live Chat Dropdown Integration:** Every saved team automatically synchronizes directly into your chat box model selector (`~/.claude/agy_providers.json`) under **`🤖 MULTI-AGENT TEAMS`** with its full composition shown (e.g., `🤖 Team: Code-Craft [Coarena:gemini-4-carbon + Groq:gpt-oss-120b]`).
- **Strict All-or-Nothing Isolation Policy:** Unlike the general failover pipeline, if **any single member** of the selected team is turned OFF, lacks keys, or throws an error/rate limit, the request **strictly halts with HTTP 503** explaining exactly which member failed. It **never leaks or cascades** into general fallback servers or standby pools.
- **Role Pipeline Execution:** Step 1 executes the lead Architect/Planner with strategic instructions; Step 2 feeds the approved blueprint into the Executor/Coder who applies full tool calling and returns the final answer.

### 2. 🤖 Modern Engine Modes (`⚡ Agentic` vs `💬 Normal`) for Anthropic & OpenAI
- Available for **both Anthropic and OpenAI** protocol servers (`⚡ Agentic` is default):
  - **`⚡ Agentic` Mode (Default):** Full bidirectional tool calling (`tool_use` / `tool_result` ↔ `tool_calls` / `role: "tool"`), streaming tool call assembly, `tool_choice`, thinking/reasoning blocks, strict OpenAI `tool_call_id` normalization (for Groq/Mistral/OpenAI), JSON Schema sanitization (for Google AI Studio/Gemini), and bidirectional **Gemini 3.x `thought_signature` round-trip caching**.
  - **`💬 Normal` Mode:** Lightweight chat experience. Automatically strips heavy coding/system prompts, skill bloat, and execution tools (saving ~10k+ tokens/turn) while **strictly preserving User Auto-Memory (`MEMORY.md`)**, **Zero Deletion & Safe Move Policy**, and **Markdown Image rendering**. Also preserves interactive clarification question tools (`ask_question` / `AskUserQuestion`) without forcing unprompted clarification loops.

### 3. 🏷️ Response Tag Signature Switch (`Tag with response: ON / OFF`)
- **Real-Time Signature Tagging:** Appends a clean metadata footer `[Server Name - Model Name]` to the end of assistant responses.
- **1-Tap Global Header Toggle:** Enable or disable signature tagging across all providers via the **`● Tag with response: ON / OFF`** button in the Console Status Bar or through the REST API (`POST /api/ui/model-signature`).

### 3. 🟢 Per-Server `ON / OFF` Switch, Fast Model Switcher & Long-Press Default
- **Per-Server `ON / OFF`:** Every server card has a compact **`● ON` / `● OFF`** toggle button in its header. Turning a server `OFF` blocks it in the proxy backend and immediately removes its models from `~/.claude/agy_providers.json`; turning it `ON` restores routing and chat dropdown sync automatically.
- **Fast Model Switcher:** Each server card includes a compact inline dropdown right next to its `📋 /id` route pill to switch the server's default model in one tap.
- **Long-Press Model Chip (~550ms):** Press and hold any model chip inside a server card to **copy the model name** to your clipboard, trigger haptic feedback, promote it to **1st position**, and set it as that server's **Default Model**.

### 4. 🛡️ Context-Preserving 5-Stage Auto History-Recovery (`Recovery: ON / OFF`)
When a long chat hits an upstream firewall/WAF or payload-size block (**HTTP `400` / `403` / `413`**) — and the request contains trimmable history — the router recovers the chat **without forcing you to open a new chat** and **without mutating your original chat history**:

| Stage | What It Sends | Why It Helps |
| :--- | :--- | :--- |
| **Original** | Full untouched chat history | Normal path (zero overhead when no error occurs) |
| **Stage 1** | Full history + **untouched last message**, shrinking only **older large `tool_result` outputs** | Keeps 100% of your conversation context intact while removing giant old logs/HTML dumps |
| **Stage 2** | Full history with **all large tool outputs & text blocks shrunk** | Recovers even when recent turns contain huge tool outputs |
| **Stage 3** | **Recent 3–5 turns** + compact **session summary** of earlier omitted history | Preserves conversation continuity while drastically reducing payload size |
| **Stage 4** | **Last assistant response + last user message** paired with full **session summary context** | Recovers extreme context-limit/WAF cases while keeping the agent aware of the prior step |
| **Stage 5** | Bare last message fallback ➔ **untouched full request** failover to next `ON` server | Seamless failover across providers if the current server refuses all stages |

> - Recovery **never** triggers on `401` (bad key), `404` (invalid model), or `429` (rate limit).
> - You can toggle this feature anytime using the **`● Recovery: ON / OFF`** switch in the Live Status Bar.

### 5. ❄️ Smart API Key Auto-Cooldown & Sticky 429 Auto-Retry
Zero-downtime rotation across multi-key pools without hammering dead or rate-limited keys:
- **Sticky Key Pointer & Instant 429 Switch:** Tracks the last healthy key per provider. When a key hits `429` (Rate Limit / Daily Quota), `401`, or `402`, the pointer immediately advances to the next healthy key and **auto-retries the request transparently**.
- **`HTTP 401` (Invalid / Revoked Key):** Placed on a **10-minute** cooldown across all models.
- **`HTTP 429` (Rate Limit / Daily Quota):** Placed on a **3-minute** cooldown (or **30-minute** cooldown if daily quota exhaustion is detected).
- **`HTTP 402` (Payment Required / Paid Model):** Only that specific **`(key + model)`** pair is placed on a **5-minute** cooldown — so the same key continues working normally for your free models.
- **Safe Fallback & Auto-Clear:** If *all* keys for a provider are in cooldown, the router still tries them so the provider never hard-locks. Any `200 OK` response or passing manual `Test` clears cooldown immediately.

### 6. 📊 Real-Time Token & Speed Meter + Custom System Prompt Presets
- **Token & Speed Meter (`tok/s`):** Automatically extracts `input_tokens`, `output_tokens`, throughput (`tok/s`), and latency (`ms`) from both Anthropic and OpenAI (SSE & JSON) responses. Displays live green speed pills (`in→out tok • ⚡ X.X tok/s • Y.Ys`) in the Console Status Bar, Live Request Feed, and per-server Live Usage cards.
- **Custom System Prompt / Presets:** Configure per-server system instructions in `✏️ Edit` with 1-tap presets (**`⚡ Concise`**, **`🇧🇩 Bengali`**, **`Clear`**). Servers with an active prompt show a purple `📝 prompt` badge on their card and prepend the instructions cleanly to both Anthropic and OpenAI requests.

### 7. 🧪 Live Concurrent Testers (60s Timeout, Progressive Updates)
- **API Keys Tester (`KEYS` ➔ `Test`):** Tests every key on a server in parallel (up to 60s timeout each). Whichever key responds first immediately displays `🟢 200 OK (ms)` or `🔴 401/402/...` right next to that key along with a live summary (`X/Y keys active`).
- **Models Compatibility Tester (`MODELS` ➔ `Select`):**
  - Discovers available models from the provider and automatically checks whether they work with your current API keys & settings.
  - Shows live status pills (`🟢 963ms`, `🔴 402`, `🔴 404`, etc.) next to every model before you add it.
  - Tap **`🟢 Only`** to filter the list down to working models only, **`Test All`** to test all visible/filtered models, or tap any individual model's status pill to test/re-test just that model.

### 8. 📡 `Console | Live Monitor` Switch Tab, Logs & Backup
- **`Console | Live Monitor` Tabs:** Zero background `/api/ui/live` polling while on `Console` (or when tab is hidden) for smooth, zero-lag mobile performance. Switch to `Live Monitor` in one tap for:
  - **📡 Live Request Feed (Top):** Reverse-chronological stream with LIVE clock pill, new-entry flash highlight, **token & speed (`tok/s`) pill**, **recovery stage**, and winning server/model/key (`✅ Passed by: ...`).
  - **⚡ Now Active (In-Flight):** Live requests currently being processed (server, model, key `#N`, stage, elapsed seconds).
  - **📊 Live Server Usage:** Per-server `OK / Fail` counts, success rate bar, token totals, `tok/s`, average latency (`ms`), recoveries, and last error.
  - **🚨 Live Issues & Cooldowns:** Real-time error list with clear root-cause explanations (`401`, `402`, `429`, `403`, `400/413`, timeouts), active cooldown countdowns, and 1-tap `Clear Cooldowns`.
- **`Logs` Button (Header):** Opens a live log viewer showing the latest 80 proxy log lines with **`Hide /status`** noise filter, **3-second Auto-Refresh**, auto-trim above 500KB, and active **Cooldown count**.
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
| **`● Tag with response: ON/OFF`** | Live Status Bar | Toggles appending the `[Server Name - Model Name]` signature footer on responses |
| **`in→out tok • ⚡ tok/s`** | Live Status Bar & Live Feed | Real-time token count, generation speed (`tok/s`), and latency meter |
| **`Sync`** | Live Status Bar | Refreshes the active route, model, token meter, and account status immediately |
| **`+ Add Key`** | Quick Key Panel | Adds a new API key to the selected provider's key pool |
| **`● ON` / `● OFF`** | Each Server Card | Hard enables/disables the server in both routing and the chat model dropdown |
| **`⚡ agentic` / `💬 normal`** | Each Server Card | Shows active engine mode (Full Tools vs Chat + Q/A token-saver); editable in `✏️ Edit` |
| **`📝 prompt`** | Each Server Card | Indicates an active Custom System Prompt / Preset configured for that server |
| **`⠿` / `▲` / `▼`** | Each Server Card | Touch-safe drag-and-drop or 1-tap reorder failover priority |
| **`💤 Standby` / `⚡ Route`** | Each Server Card | Moves server between Active Routed Pipeline and Isolated Standby Pool |
| **`📋 /server_id`** | Each Server Card | Copies the dedicated direct route URL (`http://127.0.0.1:8999/<id>`) |
| **Fast Model Dropdown** | Each Server Card | 1-tap switcher to promote any configured model to 1st / Default Model |
| **Long-Press Model Chip** | Inside Card (`MODELS`) | Hold (~550ms) on any model chip to copy its name and promote it to 1st / Default Model |
| **`✏️ Edit` / `🗑️`** | Each Server Card | Edits protocol, mode, custom headers, custom prompt presets, or safely deletes with 10s Undo |
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
├── dashboard.servers-1.js      # Server cards, ON/OFF toggle, Recovery & Tag signature toggles, key provisioning
├── dashboard.drag-1.js         # Touch & mouse drag-and-drop priority reordering
├── dashboard.modals-1.js       # Model discovery/tester, key tester, Logs modal, Backup/Restore, 10s Undo engine
├── dashboard.modals_server-1.js# Advanced settings collapsible panel, Wire API segmented switch, modal controllers
├── dashboard.live-1.js         # Console | Live tab switcher & real-time telemetry/issues/recovery feed UI
├── config.example.json         # Safe template config (tracked in Git)
└── config.json                 # Local live config with your real API keys (ignored by Git)
```

### Local HTTP API Reference
- `GET /ui` — Web Console dashboard
- `GET /status` — Active server, model, account, token counts, `tok_per_sec`, latency, and last update timestamp
- `GET /api/ui/config` — Current full router configuration
- `GET /api/ui/logs?lines=80&hide_status=1` — Tail of `proxy_v2.log` + active key cooldowns
- `GET /api/ui/live` — Live Monitor snapshot (in-flight requests, per-server stats + tokens/tps, issues with root cause, request feed with recovery stage, tokens/tps & winner, active cooldowns)
- `POST /api/ui/live-action` — Clear active cooldowns or live telemetry (`clear_cooldowns`, `clear_issues`, `clear_all`)
- `POST /api/ui/providers` / `DELETE /api/ui/providers` — Create, edit (protocol, `mode`, `wire_api`, `custom_headers`, `custom_prompt`), or delete a provider
- `POST /api/ui/provider-toggle` — Toggle a provider `ON` / `OFF` (`enabled: true | false`)
- `POST /api/ui/route-pool` — Update Active Pipeline order & Standby pool
- `POST /api/ui/keys` / `DELETE /api/ui/keys` — Add or revoke API keys
- `POST /api/ui/test-key` — Test a single API key (60s timeout) and clear its cooldown on `200 OK`
- `POST /api/ui/test-models` — Discover provider models and/or test model compatibility (60s timeout)
- `POST /api/ui/provider-models` — Add, remove, or promote/set default model to 1st position (`set_default`) on a provider
- `POST /api/ui/settings` — Update global settings (`auto_recovery: true | false`)
- `POST /api/ui/model-signature` — Toggle appending `[Server - Model]` footer tag (`show_model_signature: true | false`)
- `POST /api/ui/config-import` — Safely restore config JSON (saves `config.json.bak` first)

---

## 🛡️ Security & Privacy Notes
- `config.json`, `config.json.bak`, `*backup*.json`, and `*.log` are excluded in `.gitignore` so real API keys and logs are never pushed to GitHub.
- Keep any exported backup file containing API keys private on your local device.

---

## 📄 License
MIT License. Free to use, modify, and distribute.

# Proxy V2 Architecture & Implementation Plan (plan.md)

## Current Status
- Production directory: `~/.gemini/claude-router/` running on port `8999`.
- Backup archive: `~/.gemini/claude-router_backup_20261115_220830/` safely preserved.
- Web Dashboard live at `http://127.0.0.1:8999/ui`.
- Smart Model Auto-Detection & IPv4 Fallback active: Groq, GonkaBroker, OpenRouter, AgentRouter & Coarena verified.

## Core Features Implemented
1. **Multi-Server Configuration:**
   - Support for dynamic providers (Coarena, AgentRouter, OpenRouter, Groq, GonkaBroker, and custom servers).
   - Dynamic key management (add/revoke keys with zero server restarts).
   - Dynamic model testing & discovery with ping status badges.
2. **Two-Pool Pipeline & Standby Architecture:**
   - **⚡ ROUTED PIPELINE (ACTIVE):** Automatic failover in strict top-to-bottom priority order (#1 Primary ➔ #2 Fallback 1 ➔ #3 Fallback 2...).
   - **💤 STANDBY / FREE POOL:** Inactive servers kept on standby for on-demand use.
3. **Dedicated Direct Routing & Smart Model Routing:**
   - Every provider routes directly through its own dedicated path: `http://127.0.0.1:8999/<provider_id>`.
   - Incoming requests to `/api/v1/messages` inspect the requested model; if the model matches a specific provider (e.g. `openai/gpt-oss-120b` -> Groq, `zai-org/GLM-5.3-Flash` -> GonkaBroker), it automatically routes directly to that provider.
   - Forced IPv4 resolution to prevent Termux/Android IPv6 connection reset drops on Cloudflare-fronted providers.
4. **Touch & Drag Reordering UI:**
   - Full mobile touch drag-and-drop and desktop drag-and-drop.
   - Dedicated 1-tap `▲` (Move Up) and `▼` (Move Down) buttons.
   - 1-tap `⚡ Route` / `💤 Standby` pool switcher.
   - Real-time priority badge updates and backend synchronization.

## Active Rules Applied (from gemini.md)
1. Prior permission before removing/modifying existing working code or logic.
2. File line limit: 400 - 500 lines per file with semantic modular naming: `[basename].[logic-name]-[number].[ext]`.
3. Implementation plan presentation before starting new work.
4. Precise code replacement only.
5. Direct communication without repeating rule text.
6. Post-edit self-verification audit of existing features.
7. Continuous `plan.md` sync and audit.

## Modularization Progress (gemini.md Rule 2 & 7)
- [x] **Step 1: `proxy_v2.config-1.py`** created (231 lines) & linked into `proxy_v2.py`.
- [x] **Step 2: `proxy_v2.transform-1.py`** created (344 lines) & linked into `proxy_v2.py`.
- [x] **Step 3: `proxy_v2.forwarder-1.py`** created (335 lines) & linked into `proxy_v2.py`.
- [x] **Step 4: `proxy_v2.http_handlers-1.py`** (199 lines) & **`proxy_v2.ui_api-1.py`** (359 lines) created & linked.
- [x] **Root Server `proxy_v2.py`** slimmed down to 77 lines (orchestrating all semantic modules).
- [x] **Step 5: Modularize `dashboard.html`** into semantic modular files:
  - [x] `dashboard.styles-1.css` (153 lines - responsive styles, 2-row layout, undo toast, chip status)
  - [x] `dashboard.drag-1.js` (217 lines - touch & desktop drag-and-drop, priority reordering)
  - [x] `dashboard.servers-1.js` (294 lines - 2-row card rendering, quick keys, inline chip ping status)
  - [x] `dashboard.html` (190 lines - semantic markup with HTML confirm-modal, undo toast, custom headers)
  - [x] `dashboard.modals-1.js` (480 lines - pure HTML confirm modal, server modals, model tester, and 10s animated undo engine)
  - [x] Static asset handler added in `proxy_v2.http_handlers-1.py` serving CSS & JS modules.
- [x] **Zero Single-Click Deletion & 10s Undo System:**
  - No deletion or removal occurs in a single click across the entire UI.
  - Server delete (`openConfirmDelete`), Key revoke (`openConfirmDeleteKey`), and Model removal (`openConfirmDeleteModel`) all trigger custom HTML confirmation popups (`confirm-modal`).
  - All confirmed deletions enter a 10-second undo window with shrinking animation bar before committing to backend.
- [x] **Universal Headers & Clean Inline Ping Status:**
  - Universal Header Bag (`Originator: codex_cli_rs`, `anthropic-version`, `x-api-key`, `Authorization: Bearer`, `User-Agent`) ensures 100% discovery on strict gateways like AgentRouter.
  - Endpoint path normalization (`/v1/messages` for `/api` base URLs like Coarena) + safe token limit (4096).
  - Compact inline chip status badges (`🟢` / `🔴` / `⏳`) replacing cluttered vertical text dumps.
  - Custom headers support configurable directly from the Server modal.

## Usage Tab Implementation Progress (gemini.md Rule 2 & 7)
- [x] **Step 1: UI Hook & Slim-down:** `dashboard.html` slimmed from 497 to 470 lines; 3rd tab `📊 Usage & Quotas` button, `<div id="view-usage">` container, and `dashboard.usage-1.js` linked and deployed.
- [x] **Step 2: Backend Telemetry API (`proxy_v2.ui_usage-1.py`):** Standalone handler for `/api/ui/usage` aggregating server quotas, key health, refill countdowns, and token usage (239 lines).
- [x] **Step 3: Frontend Telemetry Engine (`dashboard.usage-1.js`):** Render KPI summary cards, server quota progress bars, granular API Key health table, and live refill tick countdown (331 lines).
- [x] **Step 4: Styling & Visual Polish (`dashboard.usage-1.css`):** Dark cybernetic theme styling for progress meters, status pills, and live countdown timers (200 lines).
- [x] **Step 5: Verification & Syntax Audit:** End-to-end verification under real traffic; live token accumulation verified in browser and backend.
- [x] **Step 6: Sync & Git Deploy:** Final plan audit and git push to main.

## Architecture Audit & Line Count Summary
All files across the entire repository are strictly under the 400-500 line limit (Rule 2):
| Module File | Line Count | Status | Logic Description |
| :--- | :---: | :---: | :--- |
| `dashboard.styles-1.css` | 494 | ✅ Pass | Mobile-first cybernetic dark UI styles, trace & playground |
| `dashboard.modals_models-1.js` | 494 | ✅ Pass | Models selector modal, model testing & ping cache |
| `proxy_v2.ui_api-1.py` | 486 | ✅ Pass | Web dashboard backend APIs & provider/key CRUD |
| `dashboard.html` | 471 | ✅ Pass | Web console semantic HTML markup & modal dialogs |
| `dashboard.servers-1.js` | 455 | ✅ Pass | Server cards rendering, status badges & direct route copier |
| `proxy_v2.multi_agent-1.py` | 447 | ✅ Pass | Multi-Agent orchestrator with step-trace telemetry |
| `proxy_v2.forwarder_loop-1.py` | 390 | ✅ Pass | Provider forwarding loop, key retry & intra-server fallback |
| `dashboard.live-1.js` | 389 | ✅ Pass | Live feed monitor, token & speed meter & trace launcher |
| `proxy_v2.ui_tester-1.py` | 385 | ✅ Pass | Model discovery, key ping tester & live telemetry actions |
| `proxy_v2.transform_anthropic-1.py` | 369 | ✅ Pass | Anthropic body sanitizer, cache limiter & thought signer |
| `proxy_v2.transform_openai-1.py` | 367 | ✅ Pass | Anthropic to OpenAI payload & JSON Schema sanitizer |
| `proxy_v2.config-1.py` | 363 | ✅ Pass | Config store, active state & Claude UI sync |
| `proxy_v2.config_live-1.py` | 359 | ✅ Pass | Live request store, error classifier & step-trace feed |
| `dashboard.modals_server-1.js` | 346 | ✅ Pass | Server modal, logs viewer modal & backup/restore |
| `dashboard.usage-1.js` | 331 | ✅ Pass | Usage & Quotas tab renderer, filters, progress bars & live timers |
| `proxy_v2.multi_agent_runner-1.py` | 322 | ✅ Pass | Team member turn executor, adaptive mode guard & key usage recorder |
| `dashboard.modals_team-1.js` | 308 | ✅ Pass | Multi-Agent team builder modal & member settings |
| `proxy_v2.transform_stream-1.py` | 304 | ✅ Pass | OpenAI SSE stream & JSON to Anthropic converter |
| `dashboard.teams-1.js` | 291 | ✅ Pass | Multi-Agent teams lane rendering, export/import & run buttons |
| `proxy_v2.http_handlers-1.py` | 287 | ✅ Pass | HTTP GET, DELETE, OPTIONS, HEAD & dynamic asset router |
| `proxy_v2.key_balancer-1.py` | 275 | ✅ Pass | Smart Key Load Balancer & Sliding 60s TPM/RPM Rotator |
| `dashboard.undo-1.js` | 273 | ✅ Pass | HTML confirmation modal & 10s animated undo deletion |
| `proxy_v2.forwarder-1.py` | 271 | ✅ Pass | Main inference router, direct routes & two-pass model parity failover |
| `proxy_v2.transform_recovery-1.py` | 261 | ✅ Pass | 5-stage context-preserving history recovery engine |
| `proxy_v2.ui_usage-1.py` | 239 | ✅ Pass | Usage telemetry endpoint aggregator & key health matrix |
| `dashboard.drag-1.js` | 224 | ✅ Pass | Touch & mouse drag-drop & priority pipeline |
| `dashboard.team_picker-1.js` | 215 | ✅ Pass | Member model dropdown panel & member model status check |
| `dashboard.usage-1.css` | 200 | ✅ Pass | Cybernetic dark UI styles for usage KPI, meters & tables |
| `dashboard.modals_playground-1.js` | 171 | ✅ Pass | In-Dashboard Multi-Agent Dry Run Playground UI modal |
| `dashboard.workflow_patterns-1.js` | 165 | ✅ Pass | 6 built-in multi-agent blueprints and workflow templates |
| `proxy_v2.ui_playground-1.py` | 155 | ✅ Pass | Multi-Agent Dry Run test API endpoint (/api/ui/team-dry-run) |
| `dashboard.chips-1.js` | 134 | ✅ Pass | Model chips fast switch, HTML escaper & long-press promoter |
| `proxy_v2.forwarder_coarena-1.py` | 131 | ✅ Pass | Coarena upstream handler & two-pass candidate routing |
| `proxy_v2.py` | 122 | ✅ Pass | Root server launcher with log janitor & IPv4 DNS patch |
| `dashboard.modals_trace-1.js` | 95 | ✅ Pass | Multi-Agent Step-Trace Timeline Modal & visualizer |
| `proxy_v2.transform-1.py` | 29 | ✅ Pass | Master transform submodules orchestrator |
| `dashboard.modals-1.js` | 8 | ✅ Pass | Master frontend modals submodules documentation stub |
| `proxy_v2.config-1.py` | 353 | ✅ Pass | Config store, active state & Claude UI sync |
| `dashboard.live-1.js` | 351 | ✅ Pass | Live feed monitor, token & speed meter & trace launcher |
| `proxy_v2.config_live-1.py` | 349 | ✅ Pass | Live request store, error classifier & step-trace feed |
| `proxy_v2.multi_agent_runner-1.py` | 322 | ✅ Pass | Team member turn executor, adaptive mode guard & key usage recorder |
| `dashboard.modals_team-1.js` | 308 | ✅ Pass | Multi-Agent team builder modal & member settings |
| `proxy_v2.transform_stream-1.py` | 304 | ✅ Pass | OpenAI SSE stream & JSON to Anthropic converter |
| `dashboard.teams-1.js` | 291 | ✅ Pass | Multi-Agent teams lane rendering, export/import & run buttons |
| `proxy_v2.http_handlers-1.py` | 282 | ✅ Pass | HTTP GET, DELETE, OPTIONS, HEAD & dynamic asset router |
| `dashboard.modals_server-1.js` | 275 | ✅ Pass | Server modal, logs viewer modal & backup/restore |
| `dashboard.undo-1.js` | 273 | ✅ Pass | HTML confirmation modal & 10s animated undo deletion |
| `proxy_v2.transform_recovery-1.py` | 261 | ✅ Pass | 5-stage context-preserving history recovery engine |
| `proxy_v2.forwarder-1.py` | 241 | ✅ Pass | Main inference router, direct routes & multi-agent dispatcher |
| `dashboard.drag-1.js` | 224 | ✅ Pass | Touch & mouse drag-drop & priority pipeline |
| `dashboard.team_picker-1.js` | 215 | ✅ Pass | Member model dropdown panel & member model status check |
| `dashboard.modals_playground-1.js` | 171 | ✅ Pass | In-Dashboard Multi-Agent Dry Run Playground UI modal |
| `dashboard.workflow_patterns-1.js` | 165 | ✅ Pass | 6 built-in multi-agent blueprints and workflow templates |
| `proxy_v2.ui_playground-1.py` | 155 | ✅ Pass | Multi-Agent Dry Run test API endpoint (/api/ui/team-dry-run) |
| `dashboard.chips-1.js` | 134 | ✅ Pass | Model chips fast switch, HTML escaper & long-press promoter |
| `proxy_v2.py` | 122 | ✅ Pass | Root server launcher with log janitor & IPv4 DNS patch |
| `dashboard.modals_trace-1.js` | 95 | ✅ Pass | Multi-Agent Step-Trace Timeline Modal & visualizer |
| `proxy_v2.key_balancer-1.py` | 151 | ✅ Pass | Smart Key Load Balancer & Sliding 60s TPM/RPM Rotator |
| `proxy_v2.transform-1.py` | 29 | ✅ Pass | Master transform submodules orchestrator |
| `dashboard.modals-1.js` | 8 | ✅ Pass | Master frontend modals submodules documentation stub |
| `README.md` | 225 | ✅ Pass | Full documentation for features, APIs & workflows |
| `crouter` | 168 | ✅ Pass | CLI daemon management tool |
| `GitHub Repository` | - | ✅ Live | https://github.com/myfunuiai-del/claude-router |


---

### [Phase 9] AntiGem App Auto-Setup & Internal Web Browser Integration (Completed)
- **Auto-Environment Detection (`ensure_cli_environment`):** Automatically detects AntiGem Linux/Termux environment on execution, creating symlinks for `crouter` and `croute` in `$PREFIX/bin` and `~/.local/bin`.
- **AntiGem Internal Web Browser Target:** Priority routing for web dashboard opening:
  1. AntiGem In-App MCP Bridge (`jarvis_open_url` / `browser_open_url`).
  2. Native Android Intent Receiver (`TermuxOpenReceiver` via `am broadcast --user 0`) ensuring opening directly inside AntiGem's internal web browser view.
  3. System fallback (`termux-open-url` / `xdg-open`).
- **File Length & Safety:** `crouter` CLI stands at 223 lines (< 500 max limit).

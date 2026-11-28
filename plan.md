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

---

### [Phase 10 - Step 1] Bounded Sticky Key Rotation (Max 5 Reqs) & Rate-Limit Pre-Check (Completed)
- **Bounded Sticky Selection (`proxy_v2.key_balancer-1.py`):**
  - Sticks to the active healthy key for at most `sticky_max_requests` (`5` by default) consecutive dispatches via `note_key_dispatch()` and `select_balanced_keys_ordered()`.
  - Automatically rotates to the next eligible key on reaching 5 consecutive dispatches, cooldown (`is_key_in_cooldown`), or per-key rate-limit (`is_key_rate_limited` checking `per_key_rpm`/`rpm` and `per_key_max_requests`).
  - Strictly excludes keys that reached configured rate limits (`[]` if all keys exhausted) so upstream quota/IP bans are prevented.
- **Forwarder Integration (`proxy_v2.forwarder_loop-1.py`, `proxy_v2.forwarder_coarena-1.py`):**
  - Added provider-level `is_provider_rate_limited` pre-check inside `try_forward_provider` (returns `False` with `429` status).
  - Passed provider config `p_info` into `_select_available_keys` and recorded `note_key_dispatch(p_id, key)` before each upstream attempt across AgentRouter, Anthropic, OpenAI, and Coarena forwarders.

### [Phase 10 - Step 2] Optional Per-Key Sticky Egress Proxy (`key_proxies` & `urlopen_for_key`) (Completed)
- **Egress Proxy Module (`proxy_v2.proxy_egress-1.py`):**
  - Optional `key_proxies` resolution (`resolve_key_proxy`) supporting dict lookup (`full key`, `key[-6:]`, `str(index)`, `'default'`) and list lookup by key index, falling back to direct connection when unconfigured.
  - Pure-stdlib HTTP/HTTPS (`ProxyHandler`) and SOCKS5/SOCKS5h (`_Socks5HTTPHandler` / `_Socks5HTTPSHandler` with optional RFC 1929 auth) opener cache (`build_opener_for_proxy` & `urlopen_for_key`).
- **Forwarder & UI Persistence (`proxy_v2.forwarder_loop-1.py`, `proxy_v2.forwarder_coarena-1.py`, `proxy_v2.multi_agent_runner-1.py`, `proxy_v2.ui_api-1.py`):**
  - Routed upstream calls through `urlopen_for_key(req, p_info=..., key=..., key_index=..., timeout=...)`.
  - Preserved `key_proxies`, `sticky_max_requests`, and `rotation_mode` on provider saves in `proxy_v2.ui_api-1.py`.

### [Phase 10 - Step 3] Per-Key Interval/Jitter, Exponential Backoff & Concurrency Guard (Completed)
- **Backoff & Per-Proxy Cooldown (`proxy_v2.config_live-1.py`):**
  - Added `parse_retry_after_seconds()` and exponential 429 backoff strikes (`60s -> 120s -> 240s -> ...`) in `mark_key_cooldown()`, reset on success by `clear_key_cooldown()`.
  - Added `mark_proxy_cooldown()`, `is_proxy_in_cooldown()`, and `clear_proxy_cooldown()` to isolate flagged sticky proxy IPs.
- **Pacing & Concurrency Guard (`proxy_v2.proxy_egress-1.py`):**
  - Added `egress_guard()` enforcing per-key & per-proxy `BoundedSemaphore` concurrency (`max_key_concurrency=2`, `max_proxy_concurrency=2`) and minimum dispatch interval + random jitter (`min_key_interval_ms=400`, `min_proxy_interval_ms=300`, `jitter_ms=250`).
- **Forwarder Wiring (`proxy_v2.forwarder_loop-1.py`, `proxy_v2.forwarder_coarena-1.py`):**
  - Combined key + proxy cooldown filtering in `_select_available_keys()`, wrapped upstream attempts in `egress_guard()`, and forwarded `Retry-After` headers into key/proxy cooldowns.

### [Phase 10 - Step 4] End-to-End Verification & Integration Audit (Completed)
- **Full Pipeline E2E Verification (`ALL_PHASE4_E2E_INTEGRATION_TESTS_PASSED`):**
  1. **5-Request Bounded Sticky + Proxy Isolation:** Requests 1–5 routed to `Key A + proxy1`, requests 6–7 rotated cleanly to `Key B + proxy2`.
  2. **`per_key_rpm` Early Rotation & Block Guard:** With `per_key_rpm=3, rpm=6`, rotated after 3 requests per key and blocked the 7th request pre-flight (`429`) without hitting upstream.
  3. **429 `Retry-After` Backoff + Instant Failover:** `429` with `Retry-After: 90` placed both key and sticky proxy IP on `90s` cooldown and failed over immediately to the healthy key + proxy within the same request.
  4. **SOCKS5 Tunnel Auth:** Verified RFC 1928/1929 `socks5h://u:p@...` forwarding through a live local SOCKS5 mock server.
- **Line-Limit & Syntax Audit:** All modified modules compile cleanly and remain under the 500-line modular limit.

---

### [Phase 11] Deprecation & Removal of Active-Chat Busy Lock and Auto-Start (Completed)
- **Busy Option Completely Removed:**
  - Removed `BUSY_NOTIF_ID`, `BUSY_INFO_FILE`, `show_busy_notification()`, and `is_other_chat_busy()` from `account_model_listener.py`. Model binding enforcement runs instantly without blocking or false-positive busy loops.
  - Removed `get_busy_status()` and `busy_info` payload from `account_lock_api.py`.
  - Removed `handleBusyLockPopup()`, `closeBusyLockModal()`, and `#busy-lock-popup-modal` UI dialog from `account_lock_ui.js` and `dashboard.html`.
- **Auto-Start Hook & Controls Removed:**
  - Removed `auto_start` toggle row and modal switcher from `dashboard.html`, `dashboard.servers-1.js`, and `dashboard.mobile-1.js`.
  - Removed `sync_autostart_bashrc()` and setting handlers from `proxy_v2.ui_api-1.py`.
  - Removed `autostart` subcommands and `~/.bashrc` script injection hooks from `crouter` CLI. Existing managed blocks in `~/.bashrc` cleaned up.

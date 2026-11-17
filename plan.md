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

## Architecture Audit & Line Count Summary
All files are strictly under the 400-500 line limit (Rule 2):
| Module File | Line Count | Status | Logic Description |
| :--- | :--- | :--- | :--- |
| `proxy_v2.py` | 84 | ✅ Pass | Root server launcher with IPv4 DNS patch |
| `config.json` | 99 | ✅ Pass | Dynamic configuration and provider storage |
| `dashboard.styles-1.css` | 153 | ✅ Pass | Mobile-first 2-row layout, safe delete, animated undo toast |
| `dashboard.html` | 190 | ✅ Pass | Web console semantic HTML markup & modals |
| `dashboard.drag-1.js` | 217 | ✅ Pass | Touch & mouse drag-drop & priority pipeline |
| `proxy_v2.http_handlers-1.py` | 226 | ✅ Pass | HTTP GET, DELETE, OPTIONS, HEAD & static assets |
| `proxy_v2.config-1.py` | 275 | ✅ Pass | Dynamic configuration, API keys, failover tracker & Claude UI auto-sync |
| `dashboard.servers-1.js` | 294 | ✅ Pass | Client cards, keys, dropdown & sync loop |
| `proxy_v2.forwarder-1.py` | 345 | ✅ Pass | Universal cascading failover on both dedicated and pipeline paths |
| `proxy_v2.transform-1.py` | 350 | ✅ Pass | SSE streaming, protocol translations & Groq 7k ITPM auto-trimmer |
| `proxy_v2.ui_api-1.py` | 389 | ✅ Pass | Web dashboard backend APIs & model ping engine |
| `dashboard.modals-1.js` | 480 | ✅ Pass | Pure HTML confirm modal & 10s unified animated undo engine |
| `README.md` | 120 | ✅ Pass | GitHub-ready documentation & quick-start guide |
| `~/.local/bin/crouter` | 68 | ✅ Pass | CLI management tool with start/stop/status/ui |
| `GitHub Repository` | - | ✅ Live | https://github.com/myfunuiai-del/claude-router |

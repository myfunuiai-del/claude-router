#!/usr/bin/env python3
import json
import os
import sys
import time
import socket
import threading
import urllib.request

# Force IPv4 resolution to prevent Termux [Errno 104] Connection reset by peer
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(*args, **kwargs):
    responses = orig_getaddrinfo(*args, **kwargs)
    ipv4_responses = [r for r in responses if r[0] == socket.AF_INET]
    return ipv4_responses if ipv4_responses else responses
socket.getaddrinfo = getaddrinfo_ipv4

PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8999
STATUS_FILE = os.path.expanduser("~/.gemini/proxy/active_status.json")
CONFIG_FILE = os.path.expanduser("~/.gemini/claude-router/config.json")
LOG_FILE = os.path.expanduser("~/.gemini/claude-router/proxy_v2.log")
DASHBOARD_HTML_FILE = os.path.expanduser("~/.gemini/claude-router/dashboard.html")

config_lock = threading.Lock()

# Process-wide shared cooldown store across dynamically loaded modules
if "_claude_router_cooldown_store" not in sys.modules:
    class _CooldownStore:
        def __init__(self):
            self.lock = threading.Lock()
            self.entries = {}  # (p_id, key_sig, scope_model) -> {"until": ts, "code": int}
    sys.modules["_claude_router_cooldown_store"] = _CooldownStore()

_COOLDOWN_STORE = sys.modules["_claude_router_cooldown_store"]

def _key_sig(key):
    if not key:
        return ""
    return f"{key[:6]}..{key[-4:]}" if len(key) > 12 else key

def _is_daily_quota_429(detail=""):
    d = (detail or "").lower()
    return any(tok in d for tok in ("insufficient_quota", "used up", "daily", "resets at"))

def mark_key_cooldown(p_id, key, code, model=None, detail=""):
    """Put a key (or key+model for 402) into temporary cooldown:
    401 -> 10m (600s); 429 daily quota -> 30m (1800s); 429 rate limit -> 3m (180s); 402 -> 5m (300s) per model.
    """
    if code == 401:
        dur, scope = 600, "*"
    elif code == 429:
        dur = 1800 if _is_daily_quota_429(detail) else 180
        scope = "*"
    elif code == 402:
        dur, scope = 300, (model or "*")
    else:
        return
    sig = _key_sig(key)
    with _COOLDOWN_STORE.lock:
        _COOLDOWN_STORE.entries[(p_id, sig, scope)] = {"until": time.time() + dur, "code": code}
    scope_lbl = f" (model={scope})" if scope != "*" else ""
    sys.stderr.write(f"[Proxy Cooldown] {p_id} key {sig}{scope_lbl} put on {dur}s cooldown (HTTP {code}).\n")

def is_key_in_cooldown(p_id, key, model=None):
    """Return remaining cooldown seconds (>0) if key is cooling down, else 0."""
    now = time.time()
    sig = _key_sig(key)
    with _COOLDOWN_STORE.lock:
        for scope in ("*", model) if model else ("*",):
            k = (p_id, sig, scope)
            info = _COOLDOWN_STORE.entries.get(k)
            if info:
                rem = info["until"] - now
                if rem > 0:
                    return int(rem)
                del _COOLDOWN_STORE.entries[k]
    return 0

def clear_key_cooldown(p_id, key, model=None):
    """Clear cooldown entries when a key succeeds or passes manual test."""
    sig = _key_sig(key)
    with _COOLDOWN_STORE.lock:
        for scope in ("*", model) if model else ("*",):
            _COOLDOWN_STORE.entries.pop((p_id, sig, scope), None)

def get_active_cooldowns():
    """Return active cooldown summaries (pruning expired entries)."""
    now = time.time()
    out = []
    with _COOLDOWN_STORE.lock:
        expired = []
        for (p_id, sig, scope), info in _COOLDOWN_STORE.entries.items():
            rem = int(info["until"] - now)
            if rem <= 0:
                expired.append((p_id, sig, scope))
            else:
                out.append({"provider": p_id, "key": sig, "scope": scope, "code": info["code"], "remaining_s": rem})
        for k in expired:
            del _COOLDOWN_STORE.entries[k]
    return out

def clear_all_cooldowns():
    """Clear all active key cooldowns immediately."""
    with _COOLDOWN_STORE.lock:
        cnt = len(_COOLDOWN_STORE.entries)
        _COOLDOWN_STORE.entries.clear()
        return cnt

# Process-wide shared Live Telemetry store across dynamically loaded modules
if "_claude_router_live_store" not in sys.modules:
    class _LiveStore:
        def __init__(self):
            self.lock = threading.Lock()
            self.in_flight = {}     # req_id -> dict
            self.server_stats = {}  # p_id -> stats dict
            self.issues = []        # newest first, max 60
            self.feed = []          # newest first, max 40
            self.seq = 0
    sys.modules["_claude_router_live_store"] = _LiveStore()

_LIVE_STORE = sys.modules["_claude_router_live_store"]

def classify_error_reason(code, detail=""):
    """Translate HTTP/network errors into clear human-readable root causes."""
    d_low = (detail or "").lower()
    if code == 401:
        return "Invalid / Revoked API Key (10m cooldown)"
    if code == 402:
        return "No Credits or Paid Model (5m model cooldown)"
    if code == 429:
        if _is_daily_quota_429(detail):
            return "Daily Free Quota Exhausted (30m cooldown)"
        return "Rate Limit Exceeded (3m cooldown)"
    if code == 403:
        if "cloudflare" in d_low or "attention required" in d_low or "waf" in d_low or "<!doctype" in d_low:
            return "Firewall / WAF Block"
        return "Forbidden / Firewall Block"
    if code == 400:
        if "context" in d_low or "token" in d_low or "too long" in d_low:
            return "Context / Token Limit Exceeded"
        return "Bad Request / Payload or History Rejected"
    if code == 404:
        return "Model or Endpoint Not Found"
    if code == 413:
        return "Payload Too Large (Oversized History)"
    if code in (500, 502, 503, 504):
        return f"Upstream Server Error / Overloaded ({code})"
    if "timed out" in d_low or "timeout" in d_low:
        return "Request Timeout (No Response)"
    if code == 0:
        return "Network / Connection Error"
    return f"HTTP Error {code}"

def set_in_flight(req_id, p_id, p_name, model, key_label="", stage="Original", path="/v1/messages"):
    with _LIVE_STORE.lock:
        existing = _LIVE_STORE.in_flight.get(req_id)
        started_at = existing["started_at"] if existing else time.time()
        _LIVE_STORE.in_flight[req_id] = {
            "id": req_id,
            "provider": p_id,
            "provider_name": p_name or p_id,
            "model": model or "unknown",
            "key_label": key_label,
            "stage": stage,
            "path": path,
            "started_at": started_at
        }

def clear_in_flight(req_id):
    with _LIVE_STORE.lock:
        _LIVE_STORE.in_flight.pop(req_id, None)

def record_live_issue(p_id, p_name, model, key_label, code, detail=""):
    now = time.time()
    reason = classify_error_reason(code, detail)
    clean_detail = (detail or "").replace("\r", " ").replace("\n", " ").strip()[:120]
    with _LIVE_STORE.lock:
        _LIVE_STORE.seq += 1
        st = _LIVE_STORE.server_stats.setdefault(p_id, {
            "provider": p_id, "name": p_name or p_id,
            "total": 0, "ok": 0, "err": 0, "recoveries": 0,
            "last_model": "", "last_key": "", "last_status": "idle",
            "last_error": "", "last_used_at": 0, "_ms_sum": 0, "_ms_cnt": 0
        })
        st["name"] = p_name or st["name"]
        st["err"] += 1
        st["total"] += 1
        st["last_model"] = model or st["last_model"]
        st["last_key"] = key_label or st["last_key"]
        st["last_status"] = "err"
        st["last_error"] = f"{code or 'ERR'}: {reason}"
        st["last_used_at"] = now

        _LIVE_STORE.issues.insert(0, {
            "id": _LIVE_STORE.seq,
            "ts": now,
            "time": time.strftime("%H:%M:%S", time.localtime(now)),
            "provider": p_id,
            "provider_name": p_name or p_id,
            "model": model or "unknown",
            "key_label": key_label or "-",
            "code": code,
            "reason": reason,
            "detail": clean_detail
        })
        if len(_LIVE_STORE.issues) > 25:
            del _LIVE_STORE.issues[25:]

def record_live_request(p_id, p_name, model, key_label, status, code, latency_ms, path="/v1/messages", recovery_stage=None, failover_from=None):
    now = time.time()
    failover_list = list(failover_from) if failover_from else []
    with _LIVE_STORE.lock:
        _LIVE_STORE.seq += 1
        if p_id and p_id != "pipeline":
            st = _LIVE_STORE.server_stats.setdefault(p_id, {
                "provider": p_id, "name": p_name or p_id,
                "total": 0, "ok": 0, "err": 0, "recoveries": 0,
                "last_model": "", "last_key": "", "last_status": "idle",
                "last_error": "", "last_used_at": 0, "_ms_sum": 0, "_ms_cnt": 0
            })
            st["name"] = p_name or st["name"]
            if status == "ok":
                st["ok"] += 1
                st["total"] += 1
                st["last_model"] = model or st["last_model"]
                st["last_key"] = key_label or st["last_key"]
                st["last_status"] = "ok"
                st["last_error"] = ""
                st["last_used_at"] = now
                if recovery_stage:
                    st["recoveries"] += 1
                if latency_ms and latency_ms > 0:
                    st["_ms_sum"] += latency_ms
                    st["_ms_cnt"] += 1

        passed_by = f"{p_name or p_id} • {model or 'unknown'} • {key_label or '-'}" if status == "ok" else "All servers failed"
        _LIVE_STORE.feed.insert(0, {
            "id": _LIVE_STORE.seq,
            "ts": now,
            "time": time.strftime("%H:%M:%S", time.localtime(now)),
            "path": path,
            "provider": p_id,
            "provider_name": p_name or p_id,
            "model": model or "unknown",
            "key_label": key_label or "-",
            "status": status,
            "code": code,
            "latency_ms": int(latency_ms or 0),
            "recovery_stage": recovery_stage or "",
            "failover_from": failover_list,
            "passed_by": passed_by
        })
        if len(_LIVE_STORE.feed) > 25:
            del _LIVE_STORE.feed[25:]

def clear_live_telemetry(kind="all"):
    with _LIVE_STORE.lock:
        _LIVE_STORE.seq += 1
        if kind in ("all", "issues"):
            _LIVE_STORE.issues.clear()
        if kind in ("all", "feed"):
            _LIVE_STORE.feed.clear()
        if kind == "all":
            _LIVE_STORE.server_stats.clear()

def get_live_snapshot():
    now = time.time()
    cfg = load_proxy_config()
    all_providers = cfg.get("providers", {})
    routed = cfg.get("routed_providers", [])
    ordered_ids = [p for p in routed if p in all_providers] + [p for p in all_providers if p not in routed]

    with _LIVE_STORE.lock:
        cur_seq = _LIVE_STORE.seq
        in_flight_list = []
        for item in _LIVE_STORE.in_flight.values():
            c = dict(item)
            c["elapsed_ms"] = int((now - item["started_at"]) * 1000)
            in_flight_list.append(c)

        servers_out = []
        for pid in ordered_ids:
            p_info = all_providers[pid]
            st = _LIVE_STORE.server_stats.get(pid, {})
            total = st.get("total", 0)
            ok = st.get("ok", 0)
            err = st.get("err", 0)
            ms_cnt = st.get("_ms_cnt", 0)
            avg_ms = int(st.get("_ms_sum", 0) / ms_cnt) if ms_cnt else 0
            success_rate = int((ok / total) * 100) if total else None
            last_ts = st.get("last_used_at", 0)
            servers_out.append({
                "id": pid,
                "name": p_info.get("name", pid),
                "enabled": p_info.get("enabled", True) is not False,
                "in_pipeline": pid in routed,
                "keys_count": len(p_info.get("keys", [])),
                "total": total,
                "ok": ok,
                "err": err,
                "recoveries": st.get("recoveries", 0),
                "success_rate": success_rate,
                "avg_ms": avg_ms,
                "last_model": st.get("last_model") or p_info.get("default_model", ""),
                "last_key": st.get("last_key", ""),
                "last_status": st.get("last_status", "idle"),
                "last_error": st.get("last_error", ""),
                "last_used_str": time.strftime("%H:%M:%S", time.localtime(last_ts)) if last_ts else "—"
            })

        issues_copy = list(_LIVE_STORE.issues)
        feed_copy = list(_LIVE_STORE.feed)

    return {
        "status": "ok",
        "seq": cur_seq,
        "now_str": time.strftime("%H:%M:%S", time.localtime(now)),
        "auto_recovery": cfg.get("auto_recovery", True) is not False,
        "active_state": active_state,
        "in_flight": in_flight_list,
        "servers": servers_out,
        "issues": issues_copy,
        "feed": feed_copy,
        "cooldowns": get_active_cooldowns()
    }

def load_proxy_config():
    """Load config from JSON file with safe fallbacks."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            sys.stderr.write(f"[Config] Error reading {CONFIG_FILE}: {e}\n")
    return {"active_provider": "coarena", "providers": {}}

def sync_to_claude_settings(cfg):
    """Automatically syncs enabled (ON) providers and models to Claude Code UI dropdown (~/.claude/agy_providers.json)."""
    try:
        claude_dir = os.path.expanduser("~/.claude")
        if not os.path.exists(claude_dir):
            return
        agy_providers_path = os.path.join(claude_dir, "agy_providers.json")
        all_providers = cfg.get("providers", {})
        routed = cfg.get("routed_providers", [])
        ordered_ids = [p for p in routed if p in all_providers] + [p for p in all_providers if p not in routed]

        providers_out = []
        for p_id in ordered_ids:
            p_info = all_providers[p_id]
            if p_info.get("enabled", True) is False:
                continue
            base_url = f"http://127.0.0.1:{PORT}/{p_id}"
            models = p_info.get("models", [])
            def_m = p_info.get("default_model") or (models[0] if models else "")
            model_list = [{"id": m} for m in models]
            if not model_list and def_m:
                model_list = [{"id": def_m}]
            p_entry = {
                "id": p_id,
                "name": f"{p_info.get('name', p_id)} ({len(p_info.get('keys', []))} API Keys)",
                "base_url": base_url,
                "api_key": "auto",
                "auth_mode": "bearer",
                "models": model_list
            }
            providers_out.append(p_entry)

        agy_data = {"providers": providers_out}
        if os.path.exists(agy_providers_path):
            try:
                with open(agy_providers_path, "r", encoding="utf-8") as f:
                    cur = json.load(f)
                    if "sessions" in cur:
                        agy_data["sessions"] = cur["sessions"]
            except Exception:
                pass

        tmp_path = agy_providers_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(agy_data, f, indent=2)
        os.replace(tmp_path, agy_providers_path)
    except Exception as e:
        sys.stderr.write(f"[Claude Sync] Warning: Could not sync to Claude settings: {e}\n")

def save_proxy_config(cfg):
    """Save config safely to JSON file and sync to Claude Code UI dropdown."""
    with config_lock:
        try:
            tmp = CONFIG_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            os.replace(tmp, CONFIG_FILE)
            sync_to_claude_settings(cfg)
            return True
        except Exception as e:
            sys.stderr.write(f"[Config] Error saving {CONFIG_FILE}: {e}\n")
            return False

def get_provider_keys(provider_id):
    """Dynamically get keys list for a provider."""
    cfg = load_proxy_config()
    p = cfg.get("providers", {}).get(provider_id, {})
    return p.get("keys", [])

# Provider key accessors
def get_coarena_keys():
    return get_provider_keys("coarena")

def get_agentrouter_key():
    keys = get_provider_keys("agentrouter")
    return keys[0] if keys else ""

def get_openrouter_keys():
    return get_provider_keys("openrouter")

def get_groq_keys():
    return get_provider_keys("groq")

def get_gonkabroker_keys():
    return get_provider_keys("gonkabroker")

current_coarena_idx = 0
current_openrouter_idx = 0
current_groq_idx = 0
current_gonka_idx = 0

active_state = {
    "server": "Coarena",
    "model": "gemini-4-carbon",
    "account": "Coarena Account #1",
    "tag": "Coarena - gemini-4-carbon",
    "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
}

def save_active_state(server, model, account):
    global active_state
    active_state = {
        "server": server,
        "model": model,
        "account": account,
        "tag": f"{server} - {model}",
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(active_state, f, indent=2)
    except Exception:
        pass

save_active_state("Coarena", "gemini-4-carbon", "Coarena Account #1")

# Initial startup sync to Claude settings
sync_to_claude_settings(load_proxy_config())

# Recovery & failover tracking
fallback_to_agentrouter = False
last_fallback_time = 0
RECOVERY_INTERVAL = 300  # 5 minutes (300s)

def test_coarena_alive():
    """Test if Coarena is alive with gemini-4-carbon or gemini-3-8-flash"""
    keys = get_coarena_keys()
    for m in ["gemini-4-carbon", "gemini-3-8-flash"]:
        body = json.dumps({'model': m, 'messages': [{'role': 'user', 'content': 'ping'}], 'max_tokens': 10}).encode('utf-8')
        for k in keys:
            req = urllib.request.Request('https://coarena.ai/api/v1/messages', data=body, headers={
                'Authorization': f'Bearer {k}',
                'x-api-key': k,
                'Content-Type': 'application/json'
            })
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        return ("Coarena", m)
            except Exception:
                continue
    return None

def test_groq_alive():
    """Test if Groq is alive with gpt-oss-120b or qwen3.8-27b"""
    keys = get_groq_keys()
    for m in ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]:
        body = json.dumps({'model': m, 'messages': [{'role': 'user', 'content': 'ping'}], 'max_tokens': 10}).encode('utf-8')
        for k in keys:
            req = urllib.request.Request('https://api.groq.com/openai/v1/chat/completions', data=body, headers={
                'Authorization': f'Bearer {k}',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            })
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        return ("Groq", m)
            except Exception:
                continue
    return None

def test_openrouter_alive():
    """Test if OpenRouter is alive with claude-haiku-5.5 or claude-sonnet-5"""
    keys = get_openrouter_keys()
    for m in ["anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5"]:
        body = json.dumps({'model': m, 'messages': [{'role': 'user', 'content': 'ping'}], 'max_tokens': 10}).encode('utf-8')
        for k in keys:
            req = urllib.request.Request('https://openrouter.ai/api/v1/messages', data=body, headers={
                'Authorization': f'Bearer {k}',
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01',
                'HTTP-Referer': 'https://antigravity.dev',
                'X-Title': 'Antigravity IDE'
            })
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        return ("OpenRouter", m)
            except Exception:
                continue
    return None

def test_gonkabroker_alive():
    """Test if GonkaBroker is alive with zai-org/GLM-5.3-Flash"""
    keys = get_gonkabroker_keys()
    m = "zai-org/GLM-5.3-Flash"
    body = json.dumps({'model': m, 'messages': [{'role': 'user', 'content': 'ping'}], 'max_tokens': 10}).encode('utf-8')
    for k in keys:
        req = urllib.request.Request('https://proxy.gonkabroker.com/v1/messages', data=body, headers={
            'x-api-key': k,
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01'
        })
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return ("GonkaBroker", m)
        except Exception:
            continue
    return None

def recovery_monitor_loop():
    """Background daemon that runs every 5 minutes when on AgentRouter fallback"""
    global fallback_to_agentrouter, last_fallback_time
    while True:
        time.sleep(15)
        if fallback_to_agentrouter and (time.time() - last_fallback_time >= RECOVERY_INTERVAL):
            sys.stderr.write("[Recovery Monitor] Checking servers sequentially: Coarena -> Groq -> OpenRouter -> GonkaBroker...\n")
            res = test_coarena_alive()
            if res:
                srv, mdl = res
                sys.stderr.write(f"[Recovery Monitor] Coarena is back online with {mdl}!\n")
                fallback_to_agentrouter = False
                save_active_state(srv, mdl, "Coarena Auto-Recovered")
                continue
            res = test_groq_alive()
            if res:
                srv, mdl = res
                sys.stderr.write(f"[Recovery Monitor] Groq is back online with {mdl}!\n")
                fallback_to_agentrouter = False
                save_active_state(srv, mdl, "Groq Auto-Recovered")
                continue
            res = test_openrouter_alive()
            if res:
                srv, mdl = res
                sys.stderr.write(f"[Recovery Monitor] OpenRouter is back online with {mdl}!\n")
                fallback_to_agentrouter = False
                save_active_state(srv, mdl, "OpenRouter Auto-Recovered")
                continue
            res = test_gonkabroker_alive()
            if res:
                srv, mdl = res
                sys.stderr.write(f"[Recovery Monitor] GonkaBroker is back online with {mdl}!\n")
                fallback_to_agentrouter = False
                save_active_state(srv, mdl, "GonkaBroker Auto-Recovered")
                continue
            last_fallback_time = time.time()

# Launch background recovery thread
recovery_thread = threading.Thread(target=recovery_monitor_loop, daemon=True)
recovery_thread.start()

MODEL_FALLBACKS = {
    "gemini-4-carbon": ["gemini-3-8-flash", "deepseek-v4-1-flash-1017"],
    "gemini-3-8-flash": ["gemini-4-carbon", "deepseek-v4-1-flash-1017"],
    "claude-sonnet-5-5": ["gemini-3-8-flash", "gemini-4-carbon", "deepseek-v4-1-flash-1017"],
    "claude-opus-5-5": ["gemini-3-8-flash", "gemini-4-carbon"],
    "claude-haiku-5-5": ["gemini-3-8-flash", "deepseek-v4-1-flash-1017"],
}

#!/usr/bin/env python3
# proxy_v2.config_live-1.py - Live telemetry store, error classification, and key cooldowns
# Modularized per gemini.md Rule 2 (Limit 400-500 lines)

import json
import os
import sys
import time
import collections
import threading

# Process-wide shared cooldown store across dynamically loaded modules
if "_claude_router_cooldown_store" not in sys.modules:
    class _CooldownStore:
        def __init__(self):
            self.lock = threading.Lock()
            self.entries = {}        # (p_id, key_sig, scope_model) -> {"until": ts, "code": int}
            self.strikes = {}        # (p_id, key_sig) -> int
            self.proxy_entries = {}  # proxy_id -> {"until": ts, "code": int, "strikes": int}
    sys.modules["_claude_router_cooldown_store"] = _CooldownStore()

_COOLDOWN_STORE = sys.modules["_claude_router_cooldown_store"]

def _key_sig(key):
    if not key:
        return ""
    return f"{key[:6]}..{key[-4:]}" if len(key) > 12 else key

def _is_daily_quota_429(detail=""):
    d = (detail or "").lower()
    return any(tok in d for tok in ("insufficient_quota", "used up", "daily", "resets at"))

def parse_retry_after_seconds(val):
    """Parse numeric Retry-After header seconds (clamped to 1..3600) or return None."""
    if val is None:
        return None
    try:
        secs = int(float(str(val).strip()))
        return max(1, min(3600, secs)) if secs > 0 else None
    except Exception:
        return None

def _proxy_id(proxy_url):
    if not proxy_url:
        return ""
    try:
        from urllib.parse import urlparse
        p = urlparse(proxy_url)
        host = p.hostname or ""
        port = f":{p.port}" if p.port else ""
        return f"{p.scheme}://{host}{port}" if host else str(proxy_url)
    except Exception:
        return str(proxy_url)

def mark_key_cooldown(p_id, key, code, model=None, detail="", retry_after=None):
    """Put a key (or key+model for 402) into temporary cooldown with exponential 429 backoff."""
    sig = _key_sig(key)
    ra_secs = parse_retry_after_seconds(retry_after)
    with _COOLDOWN_STORE.lock:
        if not hasattr(_COOLDOWN_STORE, "strikes"):
            _COOLDOWN_STORE.strikes = {}
        strikes = _COOLDOWN_STORE.strikes.get((p_id, sig), 0)
        if code == 401:
            dur, scope = 600, "*"
        elif code == 429:
            scope = "*"
            if _is_daily_quota_429(detail):
                dur = max(1800, ra_secs or 0)
            else:
                # Exponential backoff: 60s -> 120s -> 240s -> 480s -> 960s -> 1800s
                backoff = min(1800, 60 * (2 ** min(strikes, 5)))
                dur = max(backoff, ra_secs or 0)
            _COOLDOWN_STORE.strikes[(p_id, sig)] = strikes + 1
        elif code == 402:
            dur, scope = 300, (model or "*")
        else:
            return
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
    """Clear cooldown entries and backoff strikes when a key succeeds or passes manual test."""
    sig = _key_sig(key)
    with _COOLDOWN_STORE.lock:
        if hasattr(_COOLDOWN_STORE, "strikes"):
            _COOLDOWN_STORE.strikes.pop((p_id, sig), None)
        for scope in ("*", model) if model else ("*",):
            _COOLDOWN_STORE.entries.pop((p_id, sig, scope), None)

def mark_proxy_cooldown(proxy_url, code=429, retry_after=None):
    """Put a sticky egress proxy IP on temporary exponential backoff cooldown."""
    pid = _proxy_id(proxy_url)
    if not pid or code not in (403, 429, 502, 503, 504):
        return
    ra_secs = parse_retry_after_seconds(retry_after)
    with _COOLDOWN_STORE.lock:
        if not hasattr(_COOLDOWN_STORE, "proxy_entries"):
            _COOLDOWN_STORE.proxy_entries = {}
        prev = _COOLDOWN_STORE.proxy_entries.get(pid) or {}
        strikes = int(prev.get("strikes", 0))
        base = 60 if code == 429 else 30
        dur = max(min(900, base * (2 ** min(strikes, 4))), ra_secs or 0)
        _COOLDOWN_STORE.proxy_entries[pid] = {"until": time.time() + dur, "code": code, "strikes": strikes + 1}
    sys.stderr.write(f"[Proxy IP Cooldown] {pid} put on {dur}s cooldown (HTTP {code}).\n")

def is_proxy_in_cooldown(proxy_url):
    """Return remaining cooldown seconds (>0) if proxy IP is cooling down, else 0."""
    pid = _proxy_id(proxy_url)
    if not pid:
        return 0
    now = time.time()
    with _COOLDOWN_STORE.lock:
        entries = getattr(_COOLDOWN_STORE, "proxy_entries", {})
        info = entries.get(pid)
        if info:
            rem = info["until"] - now
            if rem > 0:
                return int(rem)
            del entries[pid]
    return 0

def clear_proxy_cooldown(proxy_url):
    """Reset cooldown and backoff strikes for a proxy IP after a successful request."""
    pid = _proxy_id(proxy_url)
    if not pid:
        return
    with _COOLDOWN_STORE.lock:
        entries = getattr(_COOLDOWN_STORE, "proxy_entries", {})
        entries.pop(pid, None)

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
            self.active_state = {
                "server": "Coarena",
                "model": "gemini-4-carbon",
                "account": "Coarena Account #1",
                "tag": "Coarena - gemini-4-carbon",
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
            }
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

def record_live_request(p_id, p_name, model, key_label, status, code, latency_ms, path="/v1/messages", recovery_stage=None, failover_from=None, input_tokens=0, output_tokens=0, tok_per_sec=0.0, steps_detail=None):
    now = time.time()
    failover_list = list(failover_from) if failover_from else []
    in_tok = int(input_tokens or 0)
    out_tok = int(output_tokens or 0)
    tps = round(float(tok_per_sec or 0.0), 1)
    if tps <= 0 and out_tok > 0 and latency_ms and latency_ms > 50:
        tps = round(out_tok / (latency_ms / 1000.0), 1)

    with _LIVE_STORE.lock:
        _LIVE_STORE.seq += 1
        if p_id and p_id != "pipeline":
            st = _LIVE_STORE.server_stats.setdefault(p_id, {
                "provider": p_id, "name": p_name or p_id,
                "total": 0, "ok": 0, "err": 0, "recoveries": 0,
                "last_model": "", "last_key": "", "last_status": "idle",
                "last_error": "", "last_used_at": 0, "_ms_sum": 0, "_ms_cnt": 0,
                "total_in_tokens": 0, "total_out_tokens": 0, "last_tps": 0.0
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
                st["total_in_tokens"] = st.get("total_in_tokens", 0) + in_tok
                st["total_out_tokens"] = st.get("total_out_tokens", 0) + out_tok
                if tps > 0:
                    st["last_tps"] = tps
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
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "tok_per_sec": tps,
            "recovery_stage": recovery_stage or "",
            "failover_from": failover_list,
            "passed_by": passed_by,
            "steps_detail": list(steps_detail) if steps_detail else []
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

def _calc_rl_stats(pid, p_info, now):
    fn = globals().get("get_provider_rate_limit_stats")
    if callable(fn):
        return fn(pid, p_info.get("rate_limit"), now)
    return None

def get_live_snapshot():
    now = time.time()
    _cfg_fn = globals().get("load_proxy_config")
    if callable(_cfg_fn):
        cfg = _cfg_fn()
    else:
        cfg_file = os.path.expanduser("~/.gemini/claude-router/config.json")
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
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
            rl_cfg = p_info.get("rate_limit")
            rl_stats = _calc_rl_stats(pid, p_info, now)
            servers_out.append({
                "id": pid,
                "name": p_info.get("name", pid),
                "enabled": p_info.get("enabled", True) is not False,
                "in_pipeline": pid in routed,
                "keys_count": len(p_info.get("keys", [])),
                "rate_limit": rl_cfg,
                "rate_limit_stats": rl_stats,
                "total": total,
                "ok": ok,
                "err": err,
                "recoveries": st.get("recoveries", 0),
                "success_rate": success_rate,
                "avg_ms": avg_ms,
                "total_in_tokens": st.get("total_in_tokens", 0),
                "total_out_tokens": st.get("total_out_tokens", 0),
                "last_tps": st.get("last_tps", 0.0),
                "last_model": st.get("last_model") or p_info.get("default_model", ""),
                "last_key": st.get("last_key", ""),
                "last_status": st.get("last_status", "idle"),
                "last_error": st.get("last_error", ""),
                "last_used_str": time.strftime("%H:%M:%S", time.localtime(last_ts)) if last_ts else "—"
            })

        issues_copy = list(_LIVE_STORE.issues)
        feed_copy = list(_LIVE_STORE.feed)

    _st_fn = globals().get("get_active_state")
    active_st = _st_fn() if callable(_st_fn) else {}

    return {
        "status": "ok",
        "seq": cur_seq,
        "now_str": time.strftime("%H:%M:%S", time.localtime(now)),
        "auto_recovery": cfg.get("auto_recovery", True) is not False,
        "active_state": active_st,
        "in_flight": in_flight_list,
        "servers": servers_out,
        "issues": issues_copy,
        "feed": feed_copy,
        "cooldowns": get_active_cooldowns()
    }


#!/usr/bin/env python3
# proxy_v2.ui_usage-1.py - UI Usage & Quota Analytics Telemetry Engine
# Modularized per gemini.md Rule 2 (Strictly < 500 lines)

import os
import sys
import time
import json
import importlib.util

def _load_mod(filename, target_globals):
    fp = os.path.join(os.path.dirname(__file__), filename)
    mn = filename.replace('.', '_').replace('-', '_')
    spec = importlib.util.spec_from_file_location(mn, fp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k in dir(mod):
        if not k.startswith('__'):
            target_globals[k] = getattr(mod, k)
    return mod

_cfg_mod = _load_mod("proxy_v2.config-1.py", globals())
_live_mod = _load_mod("proxy_v2.config_live-1.py", globals())
_balancer_mod = _load_mod("proxy_v2.key_balancer-1.py", globals())

def _mask_key(key):
    if not key or not isinstance(key, str):
        return "—"
    k = key.strip()
    if len(k) <= 8:
        return k[:2] + "..." + k[-2:]
    return k[:5] + "..." + k[-4:]

def _fmt_num(n):
    if not n or n <= 0:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)

def get_usage_snapshot():
    now = time.time()
    cfg = load_proxy_config()
    all_providers = cfg.get("providers", {})
    routed = cfg.get("routed_providers", [])
    ordered_ids = [p for p in routed if p in all_providers] + [p for p in all_providers if p not in routed]

    active_cooldowns = get_active_cooldowns()
    cd_map = {}
    for cd in active_cooldowns:
        # cd: {provider_id, provider_name, model, key_label, remaining_s, reason, ...}
        cd_map[(cd.get("provider_id"), cd.get("key_label"))] = cd

    servers_out = []
    keys_out = []
    model_stats = {}
    total_tokens_all = 0
    total_in_all = 0
    total_out_all = 0
    total_reqs_all = 0
    throttled_cnt = 0
    active_cnt = 0

    with _LIVE_STORE.lock:
        s_stats = dict(_LIVE_STORE.server_stats)
        feed_items = list(_LIVE_STORE.feed)

    # Calculate model usage from feed
    for f in feed_items:
        m_name = f.get("model") or "unknown"
        if m_name not in model_stats:
            model_stats[m_name] = {"requests": 0, "in_tokens": 0, "out_tokens": 0, "total_tokens": 0, "server": f.get("server", "—")}
        m_entry = model_stats[m_name]
        m_entry["requests"] += 1
        it = f.get("input_tokens", 0) or 0
        ot = f.get("output_tokens", 0) or 0
        m_entry["in_tokens"] += it
        m_entry["out_tokens"] += ot
        m_entry["total_tokens"] += (it + ot)

    for pid in ordered_ids:
        p_info = all_providers[pid]
        st = s_stats.get(pid, {})
        p_name = p_info.get("name", pid)
        is_enabled = p_info.get("enabled", True) is not False
        in_pipeline = pid in routed

        in_tok = st.get("total_in_tokens", 0)
        out_tok = st.get("total_out_tokens", 0)
        total_tok = in_tok + out_tok
        reqs = st.get("total", 0)

        total_in_all += in_tok
        total_out_all += out_tok
        total_tokens_all += total_tok
        total_reqs_all += reqs

        rl_cfg = p_info.get("rate_limit") or {}
        rl_stats = get_provider_rate_limit_stats(pid, rl_cfg, now)
        is_throttled = rl_stats.get("is_throttled", False)
        if is_throttled:
            throttled_cnt += 1
        if is_enabled:
            active_cnt += 1

        rpm_limit = rl_stats.get("rpm_limit")
        curr_rpm = rl_stats.get("rpm", 0)
        rpm_pct = min(100, int((curr_rpm / rpm_limit) * 100)) if (rpm_limit and rpm_limit > 0) else None

        win_limit = rl_stats.get("window_limit")
        curr_win = rl_stats.get("window_reqs", 0)
        win_pct = min(100, int((curr_win / win_limit) * 100)) if (win_limit and win_limit > 0) else None

        p_keys = p_info.get("keys", [])
        p_keys_usage = get_key_usage_stats(pid)

        # Build granular keys list
        for kidx, key in enumerate(p_keys):
            klbl = f"Key #{kidx+1}"
            cd_info = cd_map.get((pid, klbl))
            ksig = _balancer_mod._key_sig(key)
            kusage = p_keys_usage.get(ksig, {})

            k_status = "ready"
            k_reason = ""
            k_remaining = 0
            if cd_info:
                k_remaining = cd_info.get("remaining_s", 0)
                k_reason = cd_info.get("reason", "Cooldown active")
                k_status = "cooldown"
            elif is_throttled:
                k_status = "exhausted"
                k_reason = rl_stats.get("throttle_reason", "Quota reached")

            keys_out.append({
                "provider_id": pid,
                "provider_name": p_name,
                "key_index": kidx + 1,
                "key_label": klbl,
                "key_masked": _mask_key(key),
                "status": k_status,
                "cooldown_remaining_s": k_remaining,
                "cooldown_reason": k_reason,
                "rpm_60s": kusage.get("rpm", 0),
                "tokens_60s": kusage.get("tpm", 0),
                "total_requests": kusage.get("total_requests", 0),
                "total_tokens": kusage.get("total_tokens", 0),
                "last_used_str": time.strftime("%H:%M:%S", time.localtime(kusage["last_used"])) if kusage.get("last_used") else "—"
            })

        status_label = "Active"
        if not is_enabled:
            status_label = "Disabled"
        elif is_throttled:
            status_label = "Exhausted"
        elif not in_pipeline:
            status_label = "Standby"

        servers_out.append({
            "id": pid,
            "name": p_name,
            "type": p_info.get("type", "anthropic"),
            "mode": p_info.get("mode", "agentic"),
            "enabled": is_enabled,
            "in_pipeline": in_pipeline,
            "status_label": status_label,
            "is_throttled": is_throttled,
            "throttle_reason": rl_stats.get("throttle_reason", ""),
            "refill_seconds": rl_stats.get("refill_seconds", 0),
            "refill_text": rl_stats.get("refill_text", ""),
            "rpm": curr_rpm,
            "rpm_limit": rpm_limit,
            "rpm_percent": rpm_pct,
            "window_reqs": curr_win,
            "window_limit": win_limit,
            "window_hours": rl_stats.get("window_hours", 1),
            "window_percent": win_pct,
            "total_in_tokens": in_tok,
            "total_out_tokens": out_tok,
            "total_tokens": total_tok,
            "total_tokens_str": _fmt_num(total_tok),
            "requests_count": reqs,
            "keys_count": len(p_keys),
            "models_count": len(p_info.get("models", [])),
            "last_tps": st.get("last_tps", 0.0),
            "avg_ms": st.get("avg_ms", 0)
        })

    models_out = []
    for m_id, m_data in model_stats.items():
        models_out.append({
            "model": m_id,
            "server": m_data.get("server", "—"),
            "requests": m_data.get("requests", 0),
            "in_tokens": m_data.get("in_tokens", 0),
            "out_tokens": m_data.get("out_tokens", 0),
            "total_tokens": m_data.get("total_tokens", 0),
            "total_tokens_str": _fmt_num(m_data.get("total_tokens", 0))
        })
    models_out.sort(key=lambda x: x["total_tokens"], reverse=True)

    return {
        "status": "ok",
        "now_str": time.strftime("%H:%M:%S", time.localtime(now)),
        "kpis": {
            "total_tokens": total_tokens_all,
            "total_tokens_str": _fmt_num(total_tokens_all),
            "total_in_tokens": total_in_all,
            "total_in_tokens_str": _fmt_num(total_in_all),
            "total_out_tokens": total_out_all,
            "total_out_tokens_str": _fmt_num(total_out_all),
            "total_requests": total_reqs_all,
            "active_servers": active_cnt,
            "throttled_servers": throttled_cnt,
            "total_servers": len(all_providers),
            "cooling_keys_count": len(active_cooldowns)
        },
        "servers": servers_out,
        "keys": keys_out,
        "models": models_out
    }

def handle_ui_usage_get(handler):
    """Handles GET /api/ui/usage."""
    try:
        data = get_usage_snapshot()
        resp = json.dumps(data, ensure_ascii=False).encode('utf-8')
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json; charset=utf-8')
        handler.send_header('Content-Length', str(len(resp)))
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.end_headers()
        handler.wfile.write(resp)
        return True
    except Exception as e:
        sys.stderr.write(f"[Proxy UI Usage Error] {e}\n")
        return False

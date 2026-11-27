# proxy_v2.key_balancer-1.py - Smart Key Load Balancer & Sliding 60s Quota Rotator
# Modularized per gemini.md Rule 2 (Limit 400-500 lines)

import time
import threading
import sys
from collections import deque

WINDOW_SECONDS = 60.0
MAX_TRACK_WINDOW = 86400.0  # Retain up to 24 hours for customizable hourly/window quotas
DEFAULT_STICKY_MAX_REQUESTS = 5

def _key_sig(key):
    if not key or not isinstance(key, str):
        return ""
    return key[-6:] if len(key) >= 6 else key

# Process-wide shared key usage store
if "_claude_router_key_usage" not in sys.modules:
    class _KeyBalancerStore:
        def __init__(self):
            self.lock = threading.Lock()
            # (p_id, key_sig) -> {
            #    "requests": deque([(ts, in_tok, out_tok)]),
            #    "last_used": float,
            #    "total_requests": int,
            #    "total_tokens": int
            # }
            self.usage = {}
            self.round_robin_idx = {}
            self.upstream_resets = {}  # p_id -> float (timestamp when upstream quota resets)
            self.sticky_state = {}     # p_id -> {"key_sig": str, "count": int, "last_ts": float}
    sys.modules["_claude_router_key_usage"] = _KeyBalancerStore()

_BALANCER_STORE = sys.modules["_claude_router_key_usage"]

def _prune_entry(entry, now):
    cutoff = now - MAX_TRACK_WINDOW
    reqs = entry.get("requests")
    if reqs:
        while reqs and reqs[0][0] < cutoff:
            reqs.popleft()

def record_key_usage(p_id, key, in_tok=0, out_tok=0, now=None):
    """Registers a completed request and its consumed tokens into the 60s sliding window."""
    if not key:
        return
    now = now or time.time()
    ksig = _key_sig(key)
    with _BALANCER_STORE.lock:
        entry = _BALANCER_STORE.usage.get((p_id, ksig))
        if not entry:
            entry = {
                "requests": deque(),
                "last_used": 0.0,
                "total_requests": 0,
                "total_tokens": 0
            }
            _BALANCER_STORE.usage[(p_id, ksig)] = entry
        _prune_entry(entry, now)
        in_t = max(0, int(in_tok or 0))
        out_t = max(0, int(out_tok or 0))
        entry["requests"].append((now, in_t, out_t))
        entry["last_used"] = now
        entry["total_requests"] += 1
        entry["total_tokens"] += (in_t + out_t)

def get_key_window_stats(p_id, key, now=None):
    """Calculates active RPM and TPM in the past 60s sliding window."""
    now = now or time.time()
    ksig = _key_sig(key)
    with _BALANCER_STORE.lock:
        entry = _BALANCER_STORE.usage.get((p_id, ksig))
        if not entry:
            return {"rpm": 0, "tpm": 0, "last_used": 0.0, "total_requests": 0, "total_tokens": 0}
        _prune_entry(entry, now)
        reqs = entry["requests"]
        cutoff_60 = now - WINDOW_SECONDS
        reqs_60 = [r for r in reqs if r[0] >= cutoff_60]
        rpm = len(reqs_60)
        tpm = sum((it + ot) for _, it, ot in reqs_60)
        return {
            "rpm": rpm,
            "tpm": tpm,
            "last_used": entry.get("last_used", 0.0),
            "total_requests": entry.get("total_requests", 0),
            "total_tokens": entry.get("total_tokens", 0)
        }

def _parse_pos_int(val):
    try:
        if val is not None and str(val).strip().isdigit():
            iv = int(val)
            return iv if iv > 0 else None
    except Exception:
        pass
    return None

def get_key_rate_limit_status(p_id, key, rate_limit_cfg=None, now=None):
    """Checks per-key RPM and window request limits against configured rate_limit_cfg.
    Returns (is_limited: bool, reason: str, key_rpm: int, key_win_reqs: int).
    """
    now = now or time.time()
    rl = rate_limit_cfg or {}
    key_rpm_limit = _parse_pos_int(rl.get("per_key_rpm") or rl.get("key_rpm") or rl.get("rpm"))
    key_win_limit = _parse_pos_int(rl.get("per_key_max_requests") or rl.get("key_max_requests"))
    try:
        win_hours = max(0.1, float(rl.get("window_hours", 1)))
    except (ValueError, TypeError):
        win_hours = 1.0
    win_seconds = win_hours * 3600.0

    ksig = _key_sig(key)
    with _BALANCER_STORE.lock:
        entry = _BALANCER_STORE.usage.get((p_id, ksig))
        if not entry:
            return False, "", 0, 0
        _prune_entry(entry, now)
        reqs = entry["requests"]
        cutoff_60 = now - WINDOW_SECONDS
        cutoff_win = now - win_seconds
        key_rpm = sum(1 for r in reqs if r[0] >= cutoff_60)
        key_win = sum(1 for r in reqs if r[0] >= cutoff_win)

    if key_rpm_limit and key_rpm >= key_rpm_limit:
        return True, "key_rpm", key_rpm, key_win
    if key_win_limit and key_win >= key_win_limit:
        return True, "key_window", key_rpm, key_win
    return False, "", key_rpm, key_win

def is_key_rate_limited(p_id, key, rate_limit_cfg=None, now=None):
    """Returns (is_limited, reason) if this key has reached its configured rate limit."""
    limited, reason, _, _ = get_key_rate_limit_status(p_id, key, rate_limit_cfg, now=now)
    return limited, reason

def note_key_dispatch(p_id, key, now=None):
    """Tracks consecutive dispatches per provider key for bounded sticky rotation."""
    if not p_id or not key:
        return 0
    now = now or time.time()
    ksig = _key_sig(key)
    with _BALANCER_STORE.lock:
        if not hasattr(_BALANCER_STORE, "sticky_state"):
            _BALANCER_STORE.sticky_state = {}
        st = _BALANCER_STORE.sticky_state.get(p_id)
        if st and st.get("key_sig") == ksig:
            st["count"] = st.get("count", 0) + 1
            st["last_ts"] = now
        else:
            st = {"key_sig": ksig, "count": 1, "last_ts": now}
            _BALANCER_STORE.sticky_state[p_id] = st
        return st["count"]

def select_balanced_keys_ordered(
    p_id, keys, model=None, is_cooldown_fn=None,
    rate_limit_cfg=None, sticky_max=DEFAULT_STICKY_MAX_REQUESTS, rotation_mode="sticky"
):
    """
    Returns an ordered list of (orig_idx, key) tuples using:
      1. Rate-Limit Guard: Keys that reached configured per-key RPM/window limits are excluded.
      2. Bounded Sticky (max `sticky_max`, default 5): Sticks to current active key up to 5
         consecutive dispatches as long as it is healthy and under its rate limit.
      3. Rotation on 5-req cap / cooldown / rate-limit: Rotates to the least-loaded healthy key.
    """
    if not keys:
        return []
    # Safeguard: Deduplicate keys while preserving order
    deduped = list(dict.fromkeys(k.strip() for k in keys if isinstance(k, str) and k.strip()))
    if not deduped:
        return []
    indexed_keys = list(enumerate(deduped))
    now = time.time()

    try:
        sticky_cap = max(1, int(sticky_max if sticky_max is not None else DEFAULT_STICKY_MAX_REQUESTS))
    except (ValueError, TypeError):
        sticky_cap = DEFAULT_STICKY_MAX_REQUESTS

    eligible = []
    cooling_fallback = []
    for orig_idx, k in indexed_keys:
        cooling = 0
        if is_cooldown_fn:
            try:
                cooling = 1 if (is_cooldown_fn(p_id, k, model) > 0) else 0
            except Exception:
                cooling = 0

        is_limited, _ = is_key_rate_limited(p_id, k, rate_limit_cfg, now=now)
        if is_limited:
            # Strictly exclude keys that hit their configured rate limit to prevent upstream bans
            continue

        stats = get_key_window_stats(p_id, k, now)
        sort_tuple = (cooling, stats["rpm"], stats["tpm"], stats["last_used"], orig_idx)
        item = (orig_idx, k, _key_sig(k), sort_tuple)
        if cooling == 0:
            eligible.append(item)
        else:
            cooling_fallback.append(item)

    if not eligible:
        # All non-rate-limited keys are in cooldown (or all keys are rate-limited -> empty)
        cooling_fallback.sort(key=lambda x: x[3])
        return [(idx, k) for idx, k, _, _ in cooling_fallback]

    if rotation_mode == "round_robin" or len(eligible) == 1:
        eligible.sort(key=lambda x: x[3])
        cooling_fallback.sort(key=lambda x: x[3])
        return [(idx, k) for idx, k, _, _ in (eligible + cooling_fallback)]

    with _BALANCER_STORE.lock:
        sticky_map = getattr(_BALANCER_STORE, "sticky_state", {})
        st = sticky_map.get(p_id) or {}
        active_sig = st.get("key_sig")
        active_cnt = int(st.get("count", 0))

    active_item = next((it for it in eligible if it[2] == active_sig), None)
    if active_item and active_cnt < sticky_cap:
        # Continue bounded sticky streak on active key
        rest = sorted((it for it in eligible if it[2] != active_sig), key=lambda x: x[3])
        ordered_eligible = [active_item] + rest
    else:
        # Rotate away from active_sig (hit 5-req cap, cooldown, or rate limit)
        others = sorted((it for it in eligible if it[2] != active_sig), key=lambda x: x[3])
        ordered_eligible = others + ([active_item] if active_item else [])

    cooling_fallback.sort(key=lambda x: x[3])
    return [(idx, k) for idx, k, _, _ in (ordered_eligible + cooling_fallback)]

def select_balanced_key(p_id, keys, model=None, is_cooldown_fn=None, rate_limit_cfg=None, sticky_max=DEFAULT_STICKY_MAX_REQUESTS):
    """Selects the single best key using the bounded sticky & rate-limited algorithm."""
    ordered = select_balanced_keys_ordered(
        p_id, keys, model=model, is_cooldown_fn=is_cooldown_fn,
        rate_limit_cfg=rate_limit_cfg, sticky_max=sticky_max
    )
    if not ordered:
        return "auto"
    best_key = ordered[0][1]

    # Pre-register initial touch & sticky count so concurrent requests advance accurately
    note_key_dispatch(p_id, best_key)
    record_key_usage(p_id, best_key, in_tok=0, out_tok=0)
    return best_key

def get_key_usage_stats(p_id):
    """Returns sliding 60s RPM, TPM, lifetime requests, and last_used for a provider."""
    now = time.time()
    with _BALANCER_STORE.lock:
        res = {}
        for (pid, ksig), entry in _BALANCER_STORE.usage.items():
            if pid == p_id:
                _prune_entry(entry, now)
                reqs = entry["requests"]
                cutoff_60 = now - WINDOW_SECONDS
                reqs_60 = [r for r in reqs if r[0] >= cutoff_60]
                res[ksig] = {
                    "rpm": len(reqs_60),
                    "tpm": sum((it + ot) for _, it, ot in reqs_60),
                    "last_used": entry.get("last_used", 0.0),
                    "total_requests": entry.get("total_requests", 0),
                    "total_tokens": entry.get("total_tokens", 0)
                }
        return res

def record_upstream_rate_limit(p_id, reset_seconds):
    """Records an upstream provider rate limit reset duration from HTTP headers (e.g. Retry-After)."""
    if not p_id or reset_seconds <= 0:
        return
    reset_ts = time.time() + float(reset_seconds)
    with _BALANCER_STORE.lock:
        if not hasattr(_BALANCER_STORE, "upstream_resets"):
            _BALANCER_STORE.upstream_resets = {}
        _BALANCER_STORE.upstream_resets[p_id] = max(
            _BALANCER_STORE.upstream_resets.get(p_id, 0.0),
            reset_ts
        )

def _format_refill_time(seconds):
    """Formats refill countdown in MM:SSs or HH:MMm."""
    if seconds <= 0:
        return "00:00s"
    if seconds < 60:
        return f"00:{int(seconds):02d}s"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    if mins < 60:
        return f"{mins:02d}m {secs:02d}s"
    hrs = mins // 60
    rem_m = mins % 60
    return f"{hrs}h {rem_m:02d}m"

def get_provider_rate_limit_stats(p_id, rate_limit_cfg=None, now=None):
    """
    Computes current RPM, window requests, throttling status, and exact refill countdown.
    rate_limit_cfg schema: { 'rpm': int|null, 'max_requests': int|null, 'window_hours': float|int }
    """
    now = now or time.time()
    rl = rate_limit_cfg or {}
    rpm_val = rl.get("rpm")
    rpm_limit = int(rpm_val) if (rpm_val and str(rpm_val).isdigit() and int(rpm_val) > 0) else None

    win_val = rl.get("max_requests")
    win_limit = int(win_val) if (win_val and str(win_val).isdigit() and int(win_val) > 0) else None

    win_hours = rl.get("window_hours", 1)
    try:
        win_hours = max(0.1, float(win_hours))
    except (ValueError, TypeError):
        win_hours = 1.0
    win_seconds = win_hours * 3600.0

    all_req_ts = []
    with _BALANCER_STORE.lock:
        for (pid, _), entry in _BALANCER_STORE.usage.items():
            if pid == p_id:
                reqs = entry.get("requests", [])
                for r in reqs:
                    all_req_ts.append(r[0])
        upstream_resets = getattr(_BALANCER_STORE, "upstream_resets", {})
        up_reset_ts = upstream_resets.get(p_id, 0.0)

    # If upstream header enforced reset timer
    if up_reset_ts > now:
        refill_s = int(up_reset_ts - now)
        return {
            "rpm": 0, "rpm_limit": rpm_limit,
            "window_reqs": 0, "window_limit": win_limit, "window_hours": win_hours,
            "is_throttled": True, "throttle_reason": "upstream_header",
            "refill_seconds": refill_s, "refill_text": _format_refill_time(refill_s)
        }

    all_req_ts.sort()
    cutoff_60 = now - WINDOW_SECONDS
    cutoff_win = now - win_seconds

    reqs_60 = [t for t in all_req_ts if t >= cutoff_60]
    reqs_win = [t for t in all_req_ts if t >= cutoff_win]

    curr_rpm = len(reqs_60)
    curr_win = len(reqs_win)

    is_throttled = False
    throttle_reason = ""
    refill_s = 0

    # 1. Check RPM limit
    if rpm_limit and curr_rpm >= rpm_limit:
        is_throttled = True
        throttle_reason = "rpm"
        oldest_60 = reqs_60[0]
        refill_s = max(1, int(oldest_60 + WINDOW_SECONDS - now))

    # 2. Check Window limit (takes precedence if higher refill time)
    if win_limit and curr_win >= win_limit:
        oldest_win = reqs_win[0]
        win_refill_s = max(1, int(oldest_win + win_seconds - now))
        if win_refill_s > refill_s:
            is_throttled = True
            throttle_reason = "window"
            refill_s = win_refill_s

    return {
        "rpm": curr_rpm,
        "rpm_limit": rpm_limit,
        "window_reqs": curr_win,
        "window_limit": win_limit,
        "window_hours": win_hours,
        "is_throttled": is_throttled,
        "throttle_reason": throttle_reason,
        "refill_seconds": refill_s,
        "refill_text": _format_refill_time(refill_s) if is_throttled else ""
    }

def is_provider_rate_limited(p_id, rate_limit_cfg=None):
    """Fast boolean check if a provider is currently rate limited."""
    stats = get_provider_rate_limit_stats(p_id, rate_limit_cfg)
    return stats["is_throttled"], stats["refill_seconds"], stats["throttle_reason"]

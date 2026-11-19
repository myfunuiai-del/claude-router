# proxy_v2.key_balancer-1.py - Smart Key Load Balancer & Sliding 60s Quota Rotator
# Modularized per gemini.md Rule 2 (Limit 400-500 lines)

import time
import threading
import sys
from collections import deque

WINDOW_SECONDS = 60.0
MAX_TRACK_WINDOW = 86400.0  # Retain up to 24 hours for customizable hourly/window quotas

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

def select_balanced_keys_ordered(p_id, keys, model=None, is_cooldown_fn=None):
    """
    Returns an ordered list of (orig_idx, key) tuples based on:
      1. Cooldown priority: Non-cooling keys come first; cooling-down keys come last.
      2. Sliding 60s RPM load (fewest requests in past 60s).
      3. Sliding 60s TPM load (fewest tokens consumed in past 60s).
      4. Least Recently Used (oldest last_used timestamp, never-used keys get absolute priority).
    """
    if not keys:
        return []
    # Safeguard: Deduplicate keys while preserving order
    deduped = list(dict.fromkeys(k.strip() for k in keys if isinstance(k, str) and k.strip()))
    if not deduped:
        return []
    indexed_keys = list(enumerate(deduped))
    if len(deduped) == 1:
        return indexed_keys

    now = time.time()

    def _eval_key(idx_k):
        orig_idx, k = idx_k
        cooling = 0
        if is_cooldown_fn:
            try:
                cooling = 1 if (is_cooldown_fn(p_id, k, model) > 0) else 0
            except Exception:
                cooling = 0

        stats = get_key_window_stats(p_id, k, now)
        rpm = stats["rpm"]
        tpm = stats["tpm"]
        last_used = stats["last_used"]

        # Sort criteria tuple:
        # (cooling, rpm, tpm, last_used, orig_idx)
        # - cooling: 0 before 1 (healthy keys tried first)
        # - rpm: 0 before 1 before 2 (least requests in last 60s)
        # - tpm: least tokens in last 60s
        # - last_used: oldest used first (0.0 means never used)
        return (cooling, rpm, tpm, last_used, orig_idx)

    return sorted(indexed_keys, key=_eval_key)

def select_balanced_key(p_id, keys, model=None, is_cooldown_fn=None):
    """Selects the single best key using the balanced ordered algorithm."""
    ordered = select_balanced_keys_ordered(p_id, keys, model=model, is_cooldown_fn=is_cooldown_fn)
    if not ordered:
        return "auto"
    best_key = ordered[0][1]

    # Pre-register initial touch so back-to-back concurrent requests don't all pick the same key
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

# proxy_v2.key_balancer-1.py - Smart Key Load Balancer & Sliding 60s Quota Rotator
# Modularized per gemini.md Rule 2 (Limit 400-500 lines)

import time
import threading
import sys
from collections import deque

WINDOW_SECONDS = 60.0

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
    sys.modules["_claude_router_key_usage"] = _KeyBalancerStore()

_BALANCER_STORE = sys.modules["_claude_router_key_usage"]

def _prune_entry(entry, now):
    cutoff = now - WINDOW_SECONDS
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
        rpm = len(reqs)
        tpm = sum((it + ot) for _, it, ot in reqs)
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
                res[ksig] = {
                    "rpm": len(reqs),
                    "tpm": sum((it + ot) for _, it, ot in reqs),
                    "last_used": entry.get("last_used", 0.0),
                    "total_requests": entry.get("total_requests", 0),
                    "total_tokens": entry.get("total_tokens", 0)
                }
        return res

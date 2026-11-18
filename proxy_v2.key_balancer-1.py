# proxy_v2.key_balancer-1.py - Smart Key Load Balancer and Quota Rotator
# Modularized per gemini.md Rule 2 (Limit 400-500 lines)

import time
import threading
import sys

# Process-wide shared key usage store
if "_claude_router_key_usage" not in sys.modules:
    class _KeyBalancerStore:
        def __init__(self):
            self.lock = threading.Lock()
            # (p_id, key_sig) -> {"count": int, "last_used": float}
            self.usage = {}
            self.round_robin_idx = {}
    sys.modules["_claude_router_key_usage"] = _KeyBalancerStore()

_BALANCER_STORE = sys.modules["_claude_router_key_usage"]

def _key_sig(key):
    if not key or not isinstance(key, str):
        return ""
    return key[-6:] if len(key) >= 6 else key

def select_balanced_key(p_id, keys, model=None, is_cooldown_fn=None):
    """
    Selects the optimal API key from a list using Least-Recently-Used + Round-Robin balancing.
    Filters out keys currently in cooldown.
    """
    if not keys:
        return "auto"
    if len(keys) == 1:
        return keys[0]

    # Filter out cooling down keys if cooldown checker provided
    valid_keys = []
    for k in keys:
        if is_cooldown_fn:
            if not is_cooldown_fn(p_id, k, model):
                valid_keys.append(k)
        else:
            valid_keys.append(k)

    # If all keys in cooldown, fallback to full pool
    pool = valid_keys if valid_keys else keys
    now = time.time()

    with _BALANCER_STORE.lock:
        # Find key with least recent use within the valid pool
        best_key = None
        oldest_ts = float('inf')

        for k in pool:
            ksig = _key_sig(k)
            entry = _BALANCER_STORE.usage.get((p_id, ksig))
            if not entry:
                # Key never used yet -> highest priority!
                best_key = k
                break
            last_ts = entry.get("last_used", 0)
            if last_ts < oldest_ts:
                oldest_ts = last_ts
                best_key = k

        if not best_key:
            # Fallback round-robin index
            idx = _BALANCER_STORE.round_robin_idx.get(p_id, 0) % len(pool)
            best_key = pool[idx]
            _BALANCER_STORE.round_robin_idx[p_id] = (idx + 1) % len(pool)

        # Update usage timestamp and count
        ksig = _key_sig(best_key)
        u = _BALANCER_STORE.usage.setdefault((p_id, ksig), {"count": 0, "last_used": 0.0})
        u["count"] += 1
        u["last_used"] = now

        return best_key

def get_key_usage_stats(p_id):
    """Returns usage counts and last active times for a provider's keys."""
    with _BALANCER_STORE.lock:
        return {
            ksig: dict(data)
            for (pid, ksig), data in _BALANCER_STORE.usage.items()
            if pid == p_id
        }

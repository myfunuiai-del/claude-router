# proxy_v2.proxy_egress-1.py - Optional Per-Key Egress Proxy Router (HTTP/HTTPS/SOCKS5)
# Modularized per gemini.md Rule 2 (Limit 400-500 lines)

import http.client
import random
import socket
import ssl
import struct
import sys
import threading
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager

_OPENER_LOCK = threading.Lock()
_OPENER_CACHE = {}

DEFAULT_MIN_KEY_INTERVAL_MS = 400
DEFAULT_JITTER_MS = 250
DEFAULT_MIN_PROXY_INTERVAL_MS = 300
DEFAULT_MAX_KEY_CONCURRENCY = 2
DEFAULT_MAX_PROXY_CONCURRENCY = 2

if "_claude_router_egress_guard" not in sys.modules:
    class _EgressGuardStore:
        def __init__(self):
            self.lock = threading.Lock()
            self.next_slot = {}   # scope_key -> float (next allowed dispatch timestamp)
            self.semaphores = {}  # (kind, scope_key, limit) -> BoundedSemaphore
    sys.modules["_claude_router_egress_guard"] = _EgressGuardStore()

_GUARD_STORE = sys.modules["_claude_router_egress_guard"]

def resolve_key_proxy(p_info, key, key_index=None):
    """Resolve optional upstream proxy URL for a given provider key.
    Lookup order for dict key_proxies: exact key -> key[-6:] -> str(key_index) -> 'default'.
    For list key_proxies: key_proxies[key_index]. Returns None when unconfigured.
    """
    if not p_info or not isinstance(p_info, dict):
        return None
    kp = p_info.get("key_proxies")
    if not kp:
        return None

    proxy_val = None
    if isinstance(kp, dict):
        if key and key in kp:
            proxy_val = kp.get(key)
        elif key and isinstance(key, str):
            ksig = key[-6:] if len(key) >= 6 else key
            if ksig in kp:
                proxy_val = kp.get(ksig)
        if not proxy_val and key_index is not None and str(key_index) in kp:
            proxy_val = kp.get(str(key_index))
        if not proxy_val and "default" in kp:
            proxy_val = kp.get("default")
    elif isinstance(kp, list):
        if key_index is not None and 0 <= key_index < len(kp):
            proxy_val = kp[key_index]

    if isinstance(proxy_val, str):
        proxy_val = proxy_val.strip()
        return proxy_val if proxy_val else None
    return None

def mask_proxy_url(proxy_url):
    """Mask proxy credentials for safe logging."""
    if not proxy_url:
        return "direct"
    try:
        parsed = urllib.parse.urlparse(proxy_url)
        host_port = parsed.hostname or ""
        if parsed.port:
            host_port = f"{host_port}:{parsed.port}"
        auth = "***@" if (parsed.username or parsed.password) else ""
        return f"{parsed.scheme}://{auth}{host_port}"
    except Exception:
        return "<proxy>"

def _recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("SOCKS5 proxy closed connection unexpectedly")
        buf.extend(chunk)
    return bytes(buf)

def _socks5_connect(proxy_url, target_host, target_port, timeout=30):
    """Open a TCP tunnel to (target_host, target_port) via a SOCKS5/SOCKS5h proxy using stdlib."""
    parsed = urllib.parse.urlparse(proxy_url)
    p_host = parsed.hostname
    p_port = parsed.port or 1080
    if not p_host:
        raise ValueError(f"Invalid SOCKS5 proxy URL: {mask_proxy_url(proxy_url)}")

    sock = socket.create_connection((p_host, p_port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        user = urllib.parse.unquote(parsed.username or "")
        pwd = urllib.parse.unquote(parsed.password or "")
        has_auth = bool(user or pwd)

        # Greeting: support No-Auth (0x00) and Username/Password (0x02) if credentials given
        methods = b"\x00\x02" if has_auth else b"\x00"
        sock.sendall(struct.pack("!BB", 0x05, len(methods)) + methods)
        ver, chosen = struct.unpack("!BB", _recv_exact(sock, 2))
        if ver != 0x05 or chosen == 0xFF:
            raise ConnectionError("SOCKS5 proxy rejected authentication methods")

        if chosen == 0x02:
            if not has_auth:
                raise ConnectionError("SOCKS5 proxy requires username/password")
            ub = user.encode("utf-8")
            pb = pwd.encode("utf-8")
            sock.sendall(struct.pack("!BB", 0x01, len(ub)) + ub + struct.pack("!B", len(pb)) + pb)
            aver, status = struct.unpack("!BB", _recv_exact(sock, 2))
            if aver != 0x01 or status != 0x00:
                raise ConnectionError("SOCKS5 username/password authentication failed")

        # CONNECT request (use IPv4 literal if valid IPv4, else domain ATYP 0x03 for remote DNS)
        try:
            ip_bytes = socket.inet_aton(target_host)
            addr_part = b"\x01" + ip_bytes
        except OSError:
            hb = target_host.encode("idna")
            addr_part = b"\x03" + struct.pack("!B", len(hb)) + hb

        sock.sendall(b"\x05\x01\x00" + addr_part + struct.pack("!H", int(target_port)))
        rep_hdr = _recv_exact(sock, 4)
        if rep_hdr[0] != 0x05 or rep_hdr[1] != 0x00:
            raise ConnectionError(f"SOCKS5 CONNECT failed with reply code {rep_hdr[1]}")

        atyp = rep_hdr[3]
        if atyp == 0x01:
            _recv_exact(sock, 6)
        elif atyp == 0x03:
            alen = _recv_exact(sock, 1)[0]
            _recv_exact(sock, alen + 2)
        elif atyp == 0x04:
            _recv_exact(sock, 18)
        return sock
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        raise

class _Socks5HTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port=None, proxy_url=None, **kwargs):
        self._proxy_url = proxy_url
        super().__init__(host, port=port, **kwargs)

    def connect(self):
        self.sock = _socks5_connect(self._proxy_url, self.host, self.port, timeout=self.timeout)

class _Socks5HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port=None, proxy_url=None, **kwargs):
        self._proxy_url = proxy_url
        super().__init__(host, port=port, **kwargs)

    def connect(self):
        raw_sock = _socks5_connect(self._proxy_url, self.host, self.port, timeout=self.timeout)
        ctx = self._context if hasattr(self, "_context") else ssl.create_default_context()
        self.sock = ctx.wrap_socket(raw_sock, server_hostname=self.host)

class _Socks5HTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, proxy_url):
        super().__init__()
        self._proxy_url = proxy_url

    def http_open(self, req):
        return self.do_open(lambda h, **kw: _Socks5HTTPConnection(h, proxy_url=self._proxy_url, **kw), req)

class _Socks5HTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, proxy_url):
        super().__init__(context=ssl.create_default_context())
        self._proxy_url = proxy_url

    def https_open(self, req):
        return self.do_open(lambda h, **kw: _Socks5HTTPSConnection(h, proxy_url=self._proxy_url, **kw), req)

def build_opener_for_proxy(proxy_url):
    """Build (and cache) a urllib OpenerDirector for HTTP/HTTPS or SOCKS5/SOCKS5h proxy URLs."""
    if not proxy_url:
        return None
    with _OPENER_LOCK:
        cached = _OPENER_CACHE.get(proxy_url)
        if cached is not None:
            return cached

    scheme = urllib.parse.urlparse(proxy_url).scheme.lower()
    if scheme in ("http", "https"):
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        )
    elif scheme in ("socks5", "socks5h"):
        opener = urllib.request.build_opener(
            _Socks5HTTPHandler(proxy_url),
            _Socks5HTTPSHandler(proxy_url),
        )
    else:
        raise ValueError(f"Unsupported proxy scheme '{scheme}' in {mask_proxy_url(proxy_url)}")

    with _OPENER_LOCK:
        _OPENER_CACHE[proxy_url] = opener
    return opener

def urlopen_for_key(req, p_info=None, key=None, key_index=None, timeout=30):
    """Open URL request through the key's sticky egress proxy if configured, else direct."""
    proxy_url = resolve_key_proxy(p_info, key, key_index=key_index)
    if not proxy_url:
        return urllib.request.urlopen(req, timeout=timeout)
    opener = build_opener_for_proxy(proxy_url)
    return opener.open(req, timeout=timeout)

def _cfg_int(p_info, field, default_val, min_val=0):
    try:
        v = (p_info or {}).get(field)
        if v is None:
            return default_val
        return max(min_val, int(v))
    except (ValueError, TypeError):
        return default_val

def _get_semaphore(kind, scope_key, limit):
    with _GUARD_STORE.lock:
        skey = (kind, scope_key, limit)
        sem = _GUARD_STORE.semaphores.get(skey)
        if sem is None:
            sem = threading.BoundedSemaphore(limit)
            _GUARD_STORE.semaphores[skey] = sem
        return sem

def _reserve_pacing_delay(scope_key, min_interval_ms, jitter_ms):
    """Reserve the next dispatch slot thread-safely and return seconds to sleep outside lock."""
    if min_interval_ms <= 0 and jitter_ms <= 0:
        return 0.0
    interval_s = max(0.0, min_interval_ms / 1000.0)
    jitter_s = random.uniform(0.0, max(0.0, jitter_ms / 1000.0)) if jitter_ms > 0 else 0.0
    now = time.monotonic()
    with _GUARD_STORE.lock:
        scheduled = _GUARD_STORE.next_slot.get(scope_key, 0.0)
        if scheduled <= now:
            wait_s = 0.0
            _GUARD_STORE.next_slot[scope_key] = now + interval_s + jitter_s
        else:
            wait_s = scheduled - now
            _GUARD_STORE.next_slot[scope_key] = scheduled + interval_s + jitter_s
    return wait_s

@contextmanager
def egress_guard(p_id, p_info=None, key=None, key_index=None, acquire_timeout=30.0):
    """Enforces per-key & per-proxy concurrency limits and minimum dispatch interval + jitter."""
    ksig = (key[-6:] if len(key) >= 6 else key) if isinstance(key, str) and key else "anon"
    key_scope = f"key:{p_id}:{ksig}"
    proxy_url = resolve_key_proxy(p_info, key, key_index=key_index)
    proxy_scope = f"proxy:{mask_proxy_url(proxy_url)}" if proxy_url else None

    key_conc = _cfg_int(p_info, "max_key_concurrency", DEFAULT_MAX_KEY_CONCURRENCY, min_val=1)
    proxy_conc = _cfg_int(p_info, "max_proxy_concurrency", DEFAULT_MAX_PROXY_CONCURRENCY, min_val=1)
    min_key_ms = _cfg_int(p_info, "min_key_interval_ms", DEFAULT_MIN_KEY_INTERVAL_MS, min_val=0)
    jitter_ms = _cfg_int(p_info, "jitter_ms", DEFAULT_JITTER_MS, min_val=0)
    min_proxy_ms = _cfg_int(p_info, "min_proxy_interval_ms", DEFAULT_MIN_PROXY_INTERVAL_MS, min_val=0)

    # Fixed acquisition order (proxy -> key) prevents deadlock
    proxy_sem = _get_semaphore("proxy", proxy_scope, proxy_conc) if proxy_scope else None
    key_sem = _get_semaphore("key", key_scope, key_conc)

    proxy_acquired = False
    key_acquired = False
    try:
        if proxy_sem is not None:
            proxy_acquired = proxy_sem.acquire(timeout=acquire_timeout)
            if not proxy_acquired:
                raise TimeoutError(f"Proxy concurrency limit reached for {proxy_scope}")
        key_acquired = key_sem.acquire(timeout=acquire_timeout)
        if not key_acquired:
            raise TimeoutError(f"Key concurrency limit reached for {key_scope}")

        wait_k = _reserve_pacing_delay(key_scope, min_key_ms, jitter_ms)
        wait_p = _reserve_pacing_delay(proxy_scope, min_proxy_ms, jitter_ms) if proxy_scope else 0.0
        wait_s = max(wait_k, wait_p)
        if wait_s > 0:
            time.sleep(wait_s)
        yield proxy_url
    finally:
        if key_acquired:
            key_sem.release()
        if proxy_acquired and proxy_sem is not None:
            proxy_sem.release()


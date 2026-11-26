#!/usr/bin/env python3
import http.server
import socketserver
import socket
import ssl
import sys
import os
import importlib.util
import threading
import time

# Force IPv4 resolution to prevent Termux IPv6 broken route resets (e.g. OpenRouter/Cloudflare)
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _getaddrinfo_ipv4

def _load_module_to_globals(filename, target_globals):
    filepath = os.path.join(os.path.dirname(__file__), filename)
    mod_name = filename.replace('.', '_').replace('-', '_')
    spec = importlib.util.spec_from_file_location(mod_name, filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k in dir(mod):
        if not k.startswith('__'):
            target_globals[k] = getattr(mod, k)
    return mod

# Step 1: Config, paths, state, keys & recovery loop
_config_mod = _load_module_to_globals("proxy_v2.config-1.py", globals())

# Step 2: Protocol conversion, streaming & signature transforms
_transform_mod = _load_module_to_globals("proxy_v2.transform-1.py", globals())

# Step 3: Upstream forwarders & pipeline dispatcher
_forwarder_mod = _load_module_to_globals("proxy_v2.forwarder-1.py", globals())

# Step 4: HTTP handlers (GET, DELETE, OPTIONS, HEAD)
_http_mod = _load_module_to_globals("proxy_v2.http_handlers-1.py", globals())

# Step 5: Web UI dashboard APIs & model testing
_ui_mod = _load_module_to_globals("proxy_v2.ui_api-1.py", globals())

_NOISY_LOG_PREFIXES = ("GET /status ", "GET /api/ui/live", "GET /api/ui/logs", "GET /favicon.ico")
_MAX_LOG_BYTES = 512 * 1024  # 500 KB cap
_KEEP_LOG_LINES = 200

def trim_log_if_needed(max_bytes=_MAX_LOG_BYTES, keep_lines=_KEEP_LOG_LINES):
    """In-place truncate proxy_v2.log when it exceeds max_bytes, keeping newest lines without breaking stderr FD."""
    try:
        if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) <= max_bytes:
            return False
        with open(LOG_FILE, "r+", encoding="utf-8", errors="ignore") as f:
            tail = f.read().splitlines()[-keep_lines:]
            f.seek(0)
            f.write("\n".join(tail) + ("\n" if tail else ""))
            f.truncate()
        try:
            sys.stderr.flush()
            st_fd = os.fstat(2)
            st_file = os.stat(LOG_FILE)
            if st_fd.st_ino == st_file.st_ino and st_fd.st_dev == st_file.st_dev:
                os.lseek(2, 0, os.SEEK_END)
        except Exception:
            pass
        return True
    except Exception:
        return False

def _log_janitor_loop():
    while True:
        time.sleep(300)  # Check every 5 minutes
        trim_log_if_needed()

class UniversalProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        req_line = str(args[0]) if args else ""
        if any(req_line.startswith(p) for p in _NOISY_LOG_PREFIXES):
            return
        sys.stderr.write(f"[Proxy] {args[0]} {args[1]}\n")

    def do_OPTIONS(self):
        handle_OPTIONS(self)

    def do_HEAD(self):
        handle_HEAD(self)

    def do_GET(self):
        handle_GET(self)

    def do_DELETE(self):
        content_length = int(self.headers.get('Content-Length', 0))
        raw_body = self.rfile.read(content_length)
        handle_DELETE(self, raw_body)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        raw_body = self.rfile.read(content_length)
        if handle_ui_post(self, raw_body):
            return
        dispatch_inference(self, raw_body)

    def try_forward_provider(self, p_id, raw_body, body_obj, orig_model):
        """Attempts to forward the request to provider p_id via forwarder module."""
        return try_forward_provider(self, p_id, raw_body, body_obj, orig_model)

    def route_to_agentrouter(self, raw_body, body_obj):
        """Helper to seamlessly route to AgentRouter gpt-5.6-sol via forwarder module."""
        return route_to_agentrouter(self, raw_body, body_obj)

class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)
        self.ssl_ctx = None
        crt = os.path.join(os.path.dirname(__file__), "server.crt")
        key = os.path.join(os.path.dirname(__file__), "server.key")
        if os.path.exists(crt) and os.path.exists(key):
            try:
                ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                ctx.load_cert_chain(certfile=crt, keyfile=key)
                self.ssl_ctx = ctx
            except Exception as e:
                sys.stderr.write(f"[Proxy] Warning loading SSL certs: {e}\n")

    def get_request(self):
        newsock, fromaddr = self.socket.accept()
        if self.ssl_ctx is not None:
            try:
                # Peek first byte to see if incoming connection is TLS Handshake (0x16)
                first_byte = newsock.recv(1, socketserver.socket.MSG_PEEK)
                if first_byte == b'\x16':
                    newsock = self.ssl_ctx.wrap_socket(newsock, server_side=True)
            except Exception as e:
                pass
        return newsock, fromaddr

if __name__ == '__main__':
    trim_log_if_needed()
    threading.Thread(target=_log_janitor_loop, daemon=True).start()
    try:
        import account_model_listener
        threading.Thread(target=account_model_listener.run_listener, daemon=True).start()
    except Exception as _e:
        sys.stderr.write(f"[Proxy] Warning loading account_model_listener: {_e}\n")
    with ReusableTCPServer(('0.0.0.0', PORT), UniversalProxyHandler) as httpd:
        sys.stderr.write(f"[Proxy] Universal Bulletproof Proxy running on http://127.0.0.1:{PORT}\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass

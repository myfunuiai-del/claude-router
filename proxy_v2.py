#!/usr/bin/env python3
import http.server
import socketserver
import socket
import sys
import os
import importlib.util

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

class UniversalProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
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

if __name__ == '__main__':
    with ReusableTCPServer(('127.0.0.1', PORT), UniversalProxyHandler) as httpd:
        sys.stderr.write(f"[Proxy] Universal Bulletproof Proxy running on http://127.0.0.1:{PORT}\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass

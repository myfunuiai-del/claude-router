#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import urllib.error
import urllib.parse
import importlib.util

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

_config_mod = _load_module_to_globals("proxy_v2.config-1.py", globals())
_usage_mod = _load_module_to_globals("proxy_v2.ui_usage-1.py", globals())

def handle_OPTIONS(handler):
    """Handle CORS pre-flight requests."""
    handler.send_response(200)
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
    handler.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, x-api-key')
    handler.end_headers()

def handle_HEAD(handler):
    """Handle HEAD requests."""
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.end_headers()

def handle_GET(handler):
    """Handle GET requests for Web Dashboard, static assets, /status, and provider metadata."""
    # Static dashboard assets
    clean_p = handler.path.split('?')[0]
    if clean_p in ["/ui/demo", "/ui/demo/", "/demo", "/demo/"]:
        demo_path = os.path.join(os.path.dirname(__file__), "demo.html")
        if os.path.exists(demo_path):
            try:
                with open(demo_path, "rb") as f:
                    content = f.read()
                handler.send_response(200)
                handler.send_header('Content-Type', 'text/html; charset=utf-8')
                handler.send_header('Access-Control-Allow-Origin', '*')
                handler.send_header('Content-Length', str(len(content)))
                handler.end_headers()
                handler.wfile.write(content)
                return
            except Exception as e:
                handler.send_response(500)
                handler.end_headers()
                handler.wfile.write(f"Error serving demo: {e}".encode())
                return

    if clean_p == "/api/ui/account-lock":
        import account_lock_api
        account_lock_api.handle_account_lock_get(handler)
        return
    if (clean_p.startswith('/dashboard.') or clean_p == '/account_lock_ui.js') and (clean_p.endswith('.js') or clean_p.endswith('.css')):
        filename = clean_p.lstrip('/')
        filepath = os.path.join(os.path.dirname(__file__), filename)
        mime = "application/javascript; charset=utf-8" if filename.endswith('.js') else "text/css; charset=utf-8"
        if os.path.exists(filepath):
            try:
                with open(filepath, "rb") as f:
                    content = f.read()
                handler.send_response(200)
                handler.send_header('Content-Type', mime)
                handler.send_header('Access-Control-Allow-Origin', '*')
                handler.send_header('Content-Length', str(len(content)))
                handler.end_headers()
                handler.wfile.write(content)
                return
            except Exception as e:
                handler.send_response(500)
                handler.end_headers()
                handler.wfile.write(f"Error serving {filename}: {e}".encode())
                return

    req_clean_path = handler.path.split('?')[0]
    if req_clean_path == "/favicon.ico":
        handler.send_response(204)
        handler.end_headers()
        return

    if req_clean_path in ["/ui", "/ui/", "/dashboard", "/dashboard/"]:
        try:
            with open(DASHBOARD_HTML_FILE, "rb") as f:
                html_content = f.read()
            handler.send_response(200)
            handler.send_header('Content-Type', 'text/html; charset=utf-8')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(html_content)))
            handler.end_headers()
            handler.wfile.write(html_content)
            return
        except Exception as e:
            handler.send_response(500)
            handler.end_headers()
            handler.wfile.write(f"Error loading dashboard: {e}".encode())
            return

    if handler.path == "/api/ui/config":
        cfg = load_proxy_config()
        data = json.dumps(cfg, indent=2).encode('utf-8')
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.send_header('Content-Length', str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
        return

    if req_clean_path == "/api/ui/live":
        snap = get_live_snapshot()
        payload = json.dumps(snap, ensure_ascii=False).encode('utf-8')
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.send_header('Content-Length', str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)
        return

    if req_clean_path == "/api/ui/usage":
        if "handle_ui_usage_get" in globals() and handle_ui_usage_get(handler):
            return

    if req_clean_path == "/api/ui/logs":
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
        try:
            limit = max(10, min(300, int(qs.get("lines", ["80"])[0])))
        except Exception:
            limit = 80
        hide_status = qs.get("hide_status", ["1"])[0] not in ("0", "false", "False")

        lines = []
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    all_lines = f.read().splitlines()
                if hide_status:
                    all_lines = [
                        ln for ln in all_lines
                        if "GET /status " not in ln and "GET /api/ui/logs" not in ln and "GET /api/ui/live" not in ln
                    ]
                lines = all_lines[-limit:]
            except Exception as e:
                lines = [f"[Error reading logs: {e}]"]

        payload = json.dumps({
            "status": "ok",
            "lines": lines,
            "count": len(lines),
            "cooldowns": get_active_cooldowns()
        }, ensure_ascii=False).encode('utf-8')
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.send_header('Content-Length', str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)
        return

    if handler.path == "/status":
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        cur_active = get_active_state() if 'get_active_state' in globals() else active_state
        data = json.dumps(cur_active, indent=2).encode('utf-8')
        handler.send_header('Content-Length', str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
        return

    cfg = load_proxy_config()
    all_providers = cfg.get("providers", {})
    for p_id in all_providers:
        if handler.path == f"/{p_id}" or handler.path.startswith(f"/{p_id}/"):
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            p_obj = all_providers[p_id]
            resp = json.dumps({
                "status": "ok",
                "provider": p_id,
                "name": p_obj.get("name", p_id),
                "type": p_obj.get("type", "anthropic"),
                "default_model": p_obj.get("default_model", ""),
                "models": p_obj.get("models", [])
            }).encode('utf-8')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return

    target_path = handler.path
    if not target_path.startswith('/api'):
        target_path = '/api' + target_path
    elif target_path.startswith('/api/api'):
        target_path = target_path[4:]
    upstream_url = "https://coarena.ai" + target_path
    co_keys = get_coarena_keys()
    key = co_keys[current_coarena_idx % len(co_keys)] if co_keys else ""
    req = urllib.request.Request(upstream_url, headers={'Authorization': f"Bearer {key}", 'x-api-key': key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            handler.send_response(resp.status)
            handler.send_header('Content-Type', resp.headers.get('Content-Type', 'application/json'))
            handler.send_header('Content-Length', str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
    except urllib.error.HTTPError as e:
        err = e.read()
        handler.send_response(e.code)
        handler.send_header('Content-Length', str(len(err)))
        handler.end_headers()
        handler.wfile.write(err)

def handle_DELETE(handler, raw_body):
    """Handle DELETE requests for deleting keys or providers."""
    if handler.path == "/api/ui/keys":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            provider = data.get("provider")
            index = data.get("index")

            cfg = load_proxy_config()
            if provider in cfg.get("providers", {}):
                p = cfg["providers"][provider]
                keys = p.get("keys", [])
                if isinstance(index, int) and 0 <= index < len(keys):
                    removed = keys.pop(index)
                    save_proxy_config(cfg)
                    resp = json.dumps({"status": "ok", "message": f"Key removed from {provider}", "config": cfg}).encode()
                    handler.send_response(200)
                    handler.send_header('Content-Type', 'application/json')
                    handler.send_header('Access-Control-Allow-Origin', '*')
                    handler.send_header('Content-Length', str(len(resp)))
                    handler.end_headers()
                    handler.wfile.write(resp)
                    return
            
            handler.send_response(400)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": "Invalid provider or index"}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return

    if handler.path == "/api/ui/providers":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            provider = data.get("provider")
            cfg = load_proxy_config()
            if provider in cfg.get("providers", {}):
                del cfg["providers"][provider]
                # Clean up from routing pipelines if present
                if "routed_providers" in cfg and provider in cfg["routed_providers"]:
                    cfg["routed_providers"] = [p for p in cfg["routed_providers"] if p != provider]
                if "unrouted_providers" in cfg and provider in cfg["unrouted_providers"]:
                    cfg["unrouted_providers"] = [p for p in cfg["unrouted_providers"] if p != provider]
                if cfg.get("active_provider") == provider:
                    remaining = list(cfg.get("providers", {}).keys())
                    cfg["active_provider"] = remaining[0] if remaining else ""
                save_proxy_config(cfg)
                resp = json.dumps({"status": "ok", "message": f"Provider '{provider}' deleted", "config": cfg}).encode()
                handler.send_response(200)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                handler.send_header('Content-Length', str(len(resp)))
                handler.end_headers()
                handler.wfile.write(resp)
                return
            handler.send_response(404)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": f"Provider '{provider}' not found"}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return



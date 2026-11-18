#!/usr/bin/env python3
import os
import sys
import json
import time
import urllib.request
import urllib.error
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

def handle_ui_post(handler, raw_body):
    """Handle UI dashboard API POST requests. Returns True if handled, False otherwise."""
    # UI API: Add new key
    if handler.path == "/api/ui/keys":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            provider = data.get("provider")
            key_val = (data.get("key") or "").strip()

            if not provider or not key_val:
                handler.send_response(400)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "Provider and key are required"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            cfg = load_proxy_config()
            if provider not in cfg.get("providers", {}):
                handler.send_response(400)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": f"Provider {provider} not found"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            keys = cfg["providers"][provider].setdefault("keys", [])
            if key_val in keys:
                handler.send_response(400)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "Key already exists"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            keys.append(key_val)
            save_proxy_config(cfg)
            resp = json.dumps({"status": "ok", "message": "Key added successfully", "config": cfg}).encode()
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    # UI API: Add or Edit Provider / Server
    if handler.path == "/api/ui/providers":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            p_id = (data.get("id") or "").strip().lower()
            name = (data.get("name") or "").strip()
            base_url = (data.get("base_url") or "").strip()
            p_type = (data.get("type") or "anthropic").strip().lower()
            default_model = (data.get("default_model") or "").strip()
            models = data.get("models", [])
            keys = data.get("keys", [])

            if not p_id or not name or not base_url:
                handler.send_response(400)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "ID, Name, and Base URL are required"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            cfg = load_proxy_config()
            providers = cfg.setdefault("providers", {})
            existing_keys = providers.get(p_id, {}).get("keys", [])
            if not keys and existing_keys:
                keys = existing_keys

            custom_headers = data.get("custom_headers")
            if isinstance(custom_headers, str) and custom_headers.strip():
                try:
                    custom_headers = json.loads(custom_headers)
                except Exception:
                    custom_headers = {}
            if not isinstance(custom_headers, dict):
                custom_headers = {}

            existing_prov = providers.get(p_id, {})
            existing_enabled = existing_prov.get("enabled", True)
            existing_mode = existing_prov.get("mode", "agentic")
            p_mode = (data.get("mode") or existing_mode or "agentic").strip().lower()
            if p_mode not in ("agentic", "normal"):
                p_mode = "agentic"

            # Preserve existing models when editing via server modal (don't wipe multi-model lists)
            existing_models = existing_prov.get("models", [])
            final_models = list(existing_models) if (existing_models and len(models) <= 1) else list(models)
            eff_default = default_model or (final_models[0] if final_models else "")
            if eff_default and eff_default not in final_models:
                final_models.insert(0, eff_default)

            p_entry = {
                "name": name,
                "type": p_type,
                "mode": p_mode,
                "base_url": base_url,
                "default_model": eff_default,
                "models": final_models,
                "keys": keys,
                "enabled": data.get("enabled", existing_enabled)
            }
            if custom_headers:
                p_entry["custom_headers"] = custom_headers
            providers[p_id] = p_entry

            save_proxy_config(cfg)
            resp = json.dumps({"status": "ok", "message": f"Provider '{name}' saved successfully", "config": cfg}).encode()
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    # UI API: Fetch and Test Models for a provider
    if handler.path == "/api/ui/test-models":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            provider_id = data.get("provider")
            cfg = load_proxy_config()
            p = cfg.get("providers", {}).get(provider_id, {})
            if not p:
                handler.send_response(404)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "Provider not found"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            p_type = p.get("type", "anthropic")
            base_url = p.get("base_url", "").rstrip("/")
            keys = p.get("keys", [])
            api_key = keys[0] if keys else ""
            custom_hdrs = p.get("custom_headers", {})
            discover_only = data.get("discover_only", False)

            # Build Universal Header Bag
            universal_headers = {
                'Authorization': f'Bearer {api_key}' if api_key else '',
                'x-api-key': api_key if api_key else '',
                'anthropic-version': '2023-06-01',
                'Originator': 'codex_cli_rs',
                'User-Agent': 'codex_cli_rs/0.101.0' if provider_id == 'agentrouter' else 'Mozilla/5.0 (compatible; AI-Proxy/2.0)',
                'Content-Type': 'application/json',
                'Accept-Encoding': 'identity'
            }
            if custom_hdrs and isinstance(custom_hdrs, dict):
                universal_headers.update(custom_hdrs)

            # Resolve endpoint URLs
            if provider_id == "agentrouter":
                models_url = f"{base_url}/models"
                ping_url = f"{base_url}/messages"
            elif p_type == "openai":
                models_url = f"{base_url}/models"
                ping_url = f"{base_url}/chat/completions"
            else:
                if base_url.endswith("/api"):
                    models_url = f"{base_url}/v1/models"
                    ping_url = f"{base_url}/v1/messages"
                elif base_url.endswith("/v1") or base_url.endswith("/api/v1"):
                    models_url = f"{base_url}/models"
                    ping_url = f"{base_url}/messages"
                else:
                    models_url = f"{base_url}/v1/models"
                    ping_url = f"{base_url}/v1/messages"

            discovered_models = []
            tested_results = []
            single_model = data.get("model")

            # 1. Fetch models list only when discovering (skip when pinging a single model to stay fast!)
            if api_key and (discover_only or not single_model):
                try:
                    req = urllib.request.Request(models_url, headers=universal_headers)
                    with urllib.request.urlopen(req, timeout=8) as m_resp:
                        m_data = json.loads(m_resp.read().decode('utf-8'))
                        items = m_data.get("data") or m_data.get("models") or []
                        for it in items:
                            if isinstance(it, dict) and "id" in it:
                                discovered_models.append(it["id"])
                            elif isinstance(it, str):
                                discovered_models.append(it)
                except Exception:
                    pass

            # 2. Ping models only if NOT discover_only
            if not discover_only:
                if single_model:
                    target_models = [single_model]
                else:
                    target_models = p.get("models", [])
                    if not target_models and p.get("default_model"):
                        target_models = [p.get("default_model")]

                is_coarena = "coarena" in provider_id.lower() or "coarena.ai" in base_url
                max_tokens = 4096 if is_coarena else 10

                def ping_one(mdl):
                    if not api_key:
                        return {"model": mdl, "active": False, "code": 0, "status": "🔴 No API Key", "short": "🔴 No Key"}
                    body = json.dumps({'model': mdl, 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': max_tokens}).encode()
                    t0 = time.time()
                    try:
                        t_req = urllib.request.Request(ping_url, data=body, headers=universal_headers, method='POST')
                        with urllib.request.urlopen(t_req, timeout=60) as t_resp:
                            ms = int((time.time() - t0) * 1000)
                            if t_resp.status == 200:
                                return {"model": mdl, "active": True, "code": 200, "latency_ms": ms, "status": f"🟢 200 OK ({ms}ms)", "short": f"🟢 {ms}ms"}
                            return {"model": mdl, "active": False, "code": t_resp.status, "latency_ms": ms, "status": f"🔴 HTTP {t_resp.status}", "short": f"🔴 {t_resp.status}"}
                    except urllib.error.HTTPError as he:
                        ms = int((time.time() - t0) * 1000)
                        return {"model": mdl, "active": False, "code": he.code, "latency_ms": ms, "status": f"🔴 {he.code} {he.reason}", "short": f"🔴 {he.code}"}
                    except Exception as te:
                        ms = int((time.time() - t0) * 1000)
                        return {"model": mdl, "active": False, "code": 0, "latency_ms": ms, "status": f"🔴 Error: {str(te)[:25]}", "short": "🔴 Err"}

                import concurrent.futures
                workers = min(6, len(target_models) or 1)
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                    tested_results = list(ex.map(ping_one, target_models))

            resp = json.dumps({
                "status": "ok",
                "provider": provider_id,
                "models": tested_results,
                "all_discovered": discovered_models,
                "config": cfg
            }).encode('utf-8')

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True

        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    # UI API: Test a single API Key for a provider (60s timeout, concurrent per-key calls from UI)
    if handler.path == "/api/ui/test-key":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            provider_id = (data.get("provider") or "").strip()
            key_index = data.get("key_index")
            cfg = load_proxy_config()
            p = cfg.get("providers", {}).get(provider_id)
            if not p:
                handler.send_response(404)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "Provider not found"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            keys = p.get("keys", [])
            if not isinstance(key_index, int) or key_index < 0 or key_index >= len(keys):
                handler.send_response(400)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "Invalid key index"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            api_key = keys[key_index]
            p_type = p.get("type", "anthropic")
            base_url = p.get("base_url", "").rstrip("/")
            custom_hdrs = p.get("custom_headers", {})
            models = p.get("models", [])
            test_model = p.get("default_model") or (models[0] if models else "")

            universal_headers = {
                'Authorization': f'Bearer {api_key}',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'Originator': 'codex_cli_rs',
                'User-Agent': 'codex_cli_rs/0.101.0' if provider_id == 'agentrouter' else 'Mozilla/5.0 (compatible; AI-Proxy/2.0)',
                'Content-Type': 'application/json',
                'Accept-Encoding': 'identity'
            }
            if custom_hdrs and isinstance(custom_hdrs, dict):
                universal_headers.update(custom_hdrs)

            if provider_id == "agentrouter":
                ping_url = f"{base_url}/messages"
            elif p_type == "openai":
                ping_url = f"{base_url}/chat/completions"
            else:
                if base_url.endswith("/api"):
                    ping_url = f"{base_url}/v1/messages"
                elif base_url.endswith("/v1") or base_url.endswith("/api/v1"):
                    ping_url = f"{base_url}/messages"
                else:
                    ping_url = f"{base_url}/v1/messages"

            is_coarena = "coarena" in provider_id.lower() or "coarena.ai" in base_url
            max_tokens = 4096 if is_coarena else 10
            body = json.dumps({
                'model': test_model,
                'messages': [{'role': 'user', 'content': 'hi'}],
                'max_tokens': max_tokens
            }).encode('utf-8')

            t0 = time.time()
            active = False
            code = 0
            label = "🔴 Failed"
            detail = ""
            try:
                t_req = urllib.request.Request(ping_url, data=body, headers=universal_headers, method='POST')
                with urllib.request.urlopen(t_req, timeout=60) as t_resp:
                    code = t_resp.status
                    latency_ms = int((time.time() - t0) * 1000)
                    if code == 200:
                        active = True
                        clear_key_cooldown(provider_id, api_key, test_model)
                        label = f"🟢 200 OK ({latency_ms}ms)"
                    else:
                        label = f"🔴 HTTP {code}"
            except urllib.error.HTTPError as he:
                code = he.code
                latency_ms = int((time.time() - t0) * 1000)
                try:
                    detail = he.read().decode('utf-8', errors='ignore')[:180]
                except Exception:
                    detail = ""
                label = f"🔴 {he.code} {he.reason}"
            except Exception as te:
                latency_ms = int((time.time() - t0) * 1000)
                detail = str(te)[:120]
                label = f"🔴 {str(te)[:28]}"

            resp = json.dumps({
                "status": "ok",
                "provider": provider_id,
                "key_index": key_index,
                "model": test_model,
                "active": active,
                "code": code,
                "latency_ms": latency_ms,
                "label": label,
                "detail": detail
            }).encode('utf-8')

            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    # UI API: Add or Remove specific model from provider
    if handler.path == "/api/ui/provider-models":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            provider_id = data.get("provider")
            action = data.get("action", "add")
            model_name = (data.get("model") or "").strip()

            if not provider_id or not model_name:
                handler.send_response(400)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "Provider and model name required"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            cfg = load_proxy_config()
            p = cfg.get("providers", {}).get(provider_id)
            if not p:
                handler.send_response(404)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "Provider not found"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            models = p.setdefault("models", [])
            if action == "add":
                if model_name not in models:
                    models.append(model_name)
            elif action == "remove":
                if model_name in models:
                    models.remove(model_name)
                if p.get("default_model") == model_name:
                    p["default_model"] = models[0] if models else ""
            elif action == "set_default":
                p["default_model"] = model_name
                if model_name not in models:
                    models.append(model_name)

            save_proxy_config(cfg)
            resp = json.dumps({"status": "ok", "message": f"Model '{model_name}' updated", "config": cfg}).encode()
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    # UI API: Toggle server ON / OFF (enabled / disabled)
    if handler.path == "/api/ui/provider-toggle":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            p_id = (data.get("provider") or "").strip()
            cfg = load_proxy_config()
            p = cfg.get("providers", {}).get(p_id)
            if not p:
                handler.send_response(404)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "Provider not found"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            if "enabled" in data and isinstance(data["enabled"], bool):
                new_state = data["enabled"]
            else:
                new_state = not p.get("enabled", True)

            p["enabled"] = new_state
            save_proxy_config(cfg)
            resp = json.dumps({
                "status": "ok",
                "provider": p_id,
                "enabled": new_state,
                "message": f"{p.get('name', p_id)} turned {'ON' if new_state else 'OFF'}",
                "config": cfg
            }).encode()
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    # UI API: Move or reorder providers between Routed and Unrouted
    if handler.path == "/api/ui/route-pool":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            routed = data.get("routed_providers", [])
            unrouted = data.get("unrouted_providers", [])
            active_p = data.get("active_provider")

            cfg = load_proxy_config()
            if isinstance(routed, list):
                cfg["routed_providers"] = routed
            if isinstance(unrouted, list):
                cfg["unrouted_providers"] = unrouted
            if active_p and active_p in cfg.get("providers", {}):
                cfg["active_provider"] = active_p
            elif routed:
                cfg["active_provider"] = routed[0]

            save_proxy_config(cfg)
            resp = json.dumps({"status": "ok", "message": "Pipeline routing updated", "config": cfg}).encode()
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    # UI API: Update global router settings (e.g. auto_recovery ON/OFF)
    if handler.path == "/api/ui/settings":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            cfg = load_proxy_config()
            if "auto_recovery" in data and isinstance(data["auto_recovery"], bool):
                cfg["auto_recovery"] = data["auto_recovery"]
            save_proxy_config(cfg)
            state_txt = "ON" if cfg.get("auto_recovery", True) else "OFF"
            resp = json.dumps({
                "status": "ok",
                "message": f"Auto-Recovery turned {state_txt}",
                "config": cfg
            }).encode('utf-8')
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    # UI API: Restore / Import config JSON safely (auto-backs up existing config.json.bak first)
    if handler.path == "/api/ui/config-import":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            imported = data.get("config") if isinstance(data.get("config"), dict) else data
            if not isinstance(imported, dict) or not isinstance(imported.get("providers"), dict):
                handler.send_response(400)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "Invalid config JSON: missing 'providers' object"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            # Preserve existing keys if backup was exported without keys
            cur_cfg = load_proxy_config()
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE + ".bak", "w", encoding="utf-8") as bf:
                        json.dump(cur_cfg, bf, indent=2)
                except Exception:
                    pass

            for pid, p_obj in imported.get("providers", {}).items():
                if isinstance(p_obj, dict) and not p_obj.get("keys"):
                    old_keys = cur_cfg.get("providers", {}).get(pid, {}).get("keys", [])
                    if old_keys:
                        p_obj["keys"] = old_keys

            save_proxy_config(imported)
            resp = json.dumps({
                "status": "ok",
                "message": f"Restored {len(imported.get('providers', {}))} servers successfully",
                "config": imported
            }).encode('utf-8')
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    # UI API: Live Monitor actions (clear cooldowns / clear telemetry)
    if handler.path == "/api/ui/live-action":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            action = (data.get("action") or "").strip()
            msg = "Done"
            if action == "clear_cooldowns":
                n = clear_all_cooldowns()
                msg = f"Cleared {n} active cooldown(s)"
            elif action == "clear_issues":
                clear_live_telemetry("issues")
                msg = "Cleared live issues list"
            elif action == "clear_all":
                clear_live_telemetry("all")
                msg = "Cleared live stats, issues & feed"
            resp = json.dumps({"status": "ok", "message": msg}).encode('utf-8')
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    # Fast local token counting
    if "count_tokens" in handler.path:
        est = max(1, len(raw_body) // 4)
        resp_data = json.dumps({"input_tokens": est}).encode('utf-8')
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Content-Length', str(len(resp_data)))
        handler.end_headers()
        handler.wfile.write(resp_data)
        return True

    return False

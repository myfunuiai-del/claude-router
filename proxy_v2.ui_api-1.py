#!/usr/bin/env python3
# proxy_v2.ui_api-1.py - UI dashboard API handler (CRUD for providers, keys, teams, and settings)
# Modularized per gemini.md Rule 2 (Limit 400-500 lines)

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
_ui_tester_mod = _load_module_to_globals("proxy_v2.ui_tester-1.py", globals())

def handle_ui_post(handler, raw_body):
    """Handle UI dashboard API POST requests. Returns True if handled, False otherwise."""
    if handle_ui_tester_post(handler, raw_body):
        return True

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
            custom_prompt = data.get("custom_prompt")
            if custom_prompt is None:
                custom_prompt = existing_prov.get("custom_prompt", "")
            custom_prompt = str(custom_prompt).strip()
            if custom_prompt:
                p_entry["custom_prompt"] = custom_prompt
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
                if model_name in models:
                    models.remove(model_name)
                models.insert(0, model_name)

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

    # UI API: Toggle or set server engine mode (agentic vs normal)
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

    # UI API: Multi-Agent Teams CRUD (save, toggle, delete)
    if handler.path == "/api/ui/multi-agent-teams":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            action = data.get("action", "save")
            cfg = load_proxy_config()
            teams = cfg.setdefault("multi_agent_teams", {})

            if action == "save":
                t_id = (data.get("id") or "").strip().lower()
                t_name = (data.get("name") or "").strip()
                t_members = data.get("members", [])
                t_workflow = data.get("workflow", "role_pipeline")
                t_enabled = data.get("enabled", True)

                if not t_id or not t_name:
                    handler.send_response(400)
                    handler.send_header('Content-Type', 'application/json')
                    err = json.dumps({"status": "error", "message": "Team ID and Name are required"}).encode()
                    handler.send_header('Content-Length', str(len(err)))
                    handler.end_headers()
                    handler.wfile.write(err)
                    return True

                teams[t_id] = {
                    "id": t_id,
                    "slug": t_id,
                    "name": t_name,
                    "workflow": t_workflow,
                    "enabled": bool(t_enabled),
                    "members": t_members
                }
                save_proxy_config(cfg)
                resp = json.dumps({"status": "ok", "message": f"Team '{t_name}' saved", "config": cfg}).encode()

            elif action == "toggle":
                t_id = data.get("id")
                if t_id and t_id in teams:
                    cur = teams[t_id].get("enabled", True) is not False
                    teams[t_id]["enabled"] = not cur
                    save_proxy_config(cfg)
                    resp = json.dumps({"status": "ok", "message": f"Team '{teams[t_id]['name']}' is now {'ON' if teams[t_id]['enabled'] else 'OFF'}", "config": cfg}).encode()
                else:
                    resp = json.dumps({"status": "error", "message": "Team not found"}).encode()

            elif action == "delete":
                t_id = data.get("id")
                if t_id and t_id in teams:
                    del teams[t_id]
                    save_proxy_config(cfg)
                    resp = json.dumps({"status": "ok", "message": f"Team deleted", "config": cfg}).encode()
                else:
                    resp = json.dumps({"status": "error", "message": "Team not found"}).encode()
            else:
                resp = json.dumps({"status": "error", "message": "Invalid action"}).encode()

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
    return False

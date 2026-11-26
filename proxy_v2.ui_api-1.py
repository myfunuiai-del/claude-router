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
_ui_playground_mod = _load_module_to_globals("proxy_v2.ui_playground-1.py", globals())
_fox_brain_mod = _load_module_to_globals("proxy_v2.fox_brain-1.py", globals())
_fox_local_mod = _load_module_to_globals("proxy_v2.fox_local-1.py", globals())

def _auto_detect_model_for_server(base_url, p_type="openai", p_wire="default", custom_headers=None, api_key="", p_id=""):
    clean_base = (base_url or "").rstrip("/")
    p_wire = (p_wire or "default").lower()
    p_lower = (p_id or "").lower()
    b_lower = clean_base.lower()
    discovered = []

    # 1. Attempt live discovery via /models
    if api_key:
        try:
            if p_type == "openai":
                models_url = f"{clean_base}/models"
            else:
                models_url = f"{clean_base}/v1/models" if clean_base.endswith("/api") else f"{clean_base}/models"
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "codex_cli_rs/0.101.0" if (p_wire == "responses" or p_lower == "agentrouter") else "Mozilla/5.0"
            }
            if custom_headers and isinstance(custom_headers, dict):
                headers.update(custom_headers)
            
            req = urllib.request.Request(models_url, headers=headers)
            with urllib.request.urlopen(req, timeout=3.5) as res:
                m_data = json.loads(res.read().decode('utf-8'))
                items = m_data.get("data") or m_data.get("models") or []
                for it in items:
                    m_id = it.get("id") if isinstance(it, dict) else (it if isinstance(it, str) else None)
                    if m_id and isinstance(m_id, str):
                        if not any(m_id.startswith(pfx) for pfx in ("text-embedding", "tts-", "whisper", "dall-e")):
                            discovered.append(m_id)
                if discovered:
                    return discovered[0], discovered
        except Exception:
            pass

    # 2. Smart heuristic fallbacks
    best_fallback = "gpt-4o"
    if p_wire == "responses" or "xingchi" in p_lower or "codex" in p_lower:
        best_fallback = "gpt-6.1-sol"
    elif "deepseek" in b_lower or "deepseek" in p_lower:
        best_fallback = "deepseek-chat"
    elif "groq" in b_lower or "groq" in p_lower:
        best_fallback = "llama-3.3-70b-versatile"
    elif "cohere" in b_lower or "cohere" in p_lower:
        best_fallback = "command-r-plus"
    elif "google" in b_lower or "generativelanguage" in b_lower:
        best_fallback = "models/gemini-2.0-flash"
    elif "openrouter" in b_lower or "openrouter" in p_lower:
        best_fallback = "google/gemini-2.0-flash-exp:free"
    elif p_type == "anthropic":
        best_fallback = "claude-3-5-sonnet-20241022"
    elif p_type == "openai":
        best_fallback = "gpt-4o"

    return best_fallback, [best_fallback]

def sync_autostart_bashrc(enabled):
    """Add or remove the managed crouter-autostart block in ~/.bashrc."""
    import re
    bashrc = os.path.expanduser("~/.bashrc")
    try:
        text = ""
        if os.path.exists(bashrc):
            with open(bashrc, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        text = re.sub(r"\n?# >>> crouter-autostart >>>.*?# <<< crouter-autostart <<<\n?", "\n", text, flags=re.S)
        text = re.sub(r"\n?# Auto-start crouter background service if not running\nif \[ -x \"\$HOME/\.local/bin/crouter\" \].*?fi\n?", "\n", text, flags=re.S)
        text = text.rstrip() + "\n"
        if enabled:
            block = (
                '\n# >>> crouter-autostart >>>\n'
                'if [ -x "$HOME/.local/bin/crouter" ] && ! pgrep -f "proxy_v2.py" > /dev/null 2>&1; then\n'
                '    "$HOME/.local/bin/crouter" start > /dev/null 2>&1 &\n'
                'elif command -v crouter >/dev/null 2>&1 && ! pgrep -f "proxy_v2.py" > /dev/null 2>&1; then\n'
                '    crouter start > /dev/null 2>&1 &\n'
                'fi\n'
                '# <<< crouter-autostart <<<\n'
            )
            text = text + block
        with open(bashrc, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass

def handle_ui_post(handler, raw_body):
    """Handle UI dashboard API POST requests. Returns True if handled, False otherwise."""
    import updater_release_api
    if updater_release_api.handle_update_post(handler, raw_body):
        return True
    if updater_release_api.handle_full_restore_post(handler, raw_body):
        return True
    if handle_fox_local_installer(handler, raw_body):
        return True
    if handle_fox_brain_post(handler, raw_body) or (hasattr(_fox_brain_mod, "handle_fox_brain_post_alias") and _fox_brain_mod.handle_fox_brain_post_alias(handler, raw_body)):
        return True
    if handle_ui_tester_post(handler, raw_body):
        return True
    if handle_ui_playground_post(handler, raw_body):
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
            key_name = (data.get("name") or "").strip()
            if key_name:
                cfg["providers"][provider].setdefault("key_names", {})[key_val] = key_name
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

    if handler.path == "/api/ui/keys/rename":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            provider = data.get("provider")
            idx = int(data.get("index", -1))
            new_name = (data.get("name") or "").strip()
            cfg = load_proxy_config()
            p_obj = cfg.get("providers", {}).get(provider)
            if not p_obj or idx < 0 or idx >= len(p_obj.get("keys", [])):
                raise ValueError("Invalid provider or key index")
            key_val = p_obj["keys"][idx]
            key_names = p_obj.setdefault("key_names", {})
            if new_name:
                key_names[key_val] = new_name
            else:
                key_names.pop(key_val, None)
            save_proxy_config(cfg)
            resp = json.dumps({"status": "ok", "message": "Key renamed", "config": cfg}).encode()
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(400)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    if handler.path == "/api/ui/keys/move":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            provider = data.get("provider")
            idx = int(data.get("index", -1))
            direction = data.get("direction", "")
            cfg = load_proxy_config()
            p_obj = cfg.get("providers", {}).get(provider)
            keys = p_obj.get("keys", []) if p_obj else []
            if idx < 0 or idx >= len(keys):
                raise ValueError("Invalid key index")
            if direction == "up" and idx > 0:
                keys[idx], keys[idx - 1] = keys[idx - 1], keys[idx]
            elif direction == "down" and idx < len(keys) - 1:
                keys[idx], keys[idx + 1] = keys[idx + 1], keys[idx]
            save_proxy_config(cfg)
            resp = json.dumps({"status": "ok", "message": "Key priority updated", "config": cfg}).encode()
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(400)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    if handler.path == "/api/ui/keys/test-single":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            provider = data.get("provider")
            idx = int(data.get("index", -1))
            cfg = load_proxy_config()
            p_obj = cfg.get("providers", {}).get(provider)
            keys = p_obj.get("keys", []) if p_obj else []
            if not p_obj or idx < 0 or idx >= len(keys):
                raise ValueError("Invalid provider or key index")
            key_val = keys[idx]
            base_url = (p_obj.get("base_url") or "").rstrip("/")
            p_type = p_obj.get("type", "openai")
            test_url = f"{base_url}/models" if p_type == "openai" else (f"{base_url}/v1/models" if base_url.endswith("/api") else f"{base_url}/models")
            headers = {"Authorization": f"Bearer {key_val}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
            t0 = time.time()
            alive = False
            msg = ""
            try:
                req = urllib.request.Request(test_url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as r:
                    alive = (r.status == 200)
                    msg = f"HTTP {r.status}"
            except urllib.error.HTTPError as he:
                alive = False
                msg = f"HTTP {he.code}"
            except Exception as ex:
                alive = False
                msg = str(ex)[:40]
            latency_ms = int((time.time() - t0) * 1000)
            resp = json.dumps({"status": "ok", "alive": alive, "latency_ms": latency_ms, "message": msg}).encode()
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True
        except Exception as e:
            handler.send_response(400)
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
            existing_wire = existing_prov.get("wire_api", "default")
            p_wire = (data.get("wire_api") or existing_wire or "default").strip().lower()
            if p_wire not in ("default", "responses"):
                p_wire = "default"

            # Preserve existing models when editing via server modal (don't wipe multi-model lists)
            existing_models = existing_prov.get("models", [])
            final_models = list(existing_models) if (existing_models and len(models) <= 1) else list(models)
            eff_default = default_model or (final_models[0] if final_models else "")
            if not eff_default:
                detected_m, discovered = _auto_detect_model_for_server(
                    base_url=base_url,
                    p_type=p_type,
                    p_wire=p_wire,
                    custom_headers=custom_headers,
                    api_key=(keys[0] if keys else ""),
                    p_id=p_id
                )
                eff_default = detected_m
                if discovered:
                    for dm in discovered:
                        if dm not in final_models:
                            final_models.append(dm)

            if eff_default and eff_default not in final_models:
                final_models.insert(0, eff_default)
            if not final_models and eff_default:
                final_models = [eff_default]

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
            if p_wire != "default":
                p_entry["wire_api"] = p_wire
            if custom_headers:
                p_entry["custom_headers"] = custom_headers
            custom_prompt = data.get("custom_prompt")
            if custom_prompt is None:
                custom_prompt = existing_prov.get("custom_prompt", "")
            custom_prompt = str(custom_prompt).strip()
            if custom_prompt:
                p_entry["custom_prompt"] = custom_prompt
            rl = data.get("rate_limit")
            if isinstance(rl, dict):
                p_entry["rate_limit"] = rl
            elif "rate_limit" in existing_prov:
                p_entry["rate_limit"] = existing_prov["rate_limit"]
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
    # UI API: Update global router settings (e.g. auto_recovery ON/OFF, show_model_signature ON/OFF)
    if handler.path == "/api/ui/settings":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            cfg = load_proxy_config()
            msgs = []
            if "auto_recovery" in data and isinstance(data["auto_recovery"], bool):
                cfg["auto_recovery"] = data["auto_recovery"]
                msgs.append(f"Auto-Recovery turned {'ON' if data['auto_recovery'] else 'OFF'}")
            if "show_model_signature" in data and isinstance(data["show_model_signature"], bool):
                cfg["show_model_signature"] = data["show_model_signature"]
                msgs.append(f"Tag with response turned {'ON' if data['show_model_signature'] else 'OFF'}")
            if "auto_start" in data and isinstance(data["auto_start"], bool):
                cfg["auto_start"] = data["auto_start"]
                sync_autostart_bashrc(data["auto_start"])
                msgs.append(f"Auto-Start on Launch turned {'ON' if data['auto_start'] else 'OFF'}")
            save_proxy_config(cfg)
            resp = json.dumps({
                "status": "ok",
                "message": ", ".join(msgs) if msgs else "Settings updated",
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
    # UI API: Full Uninstall (removes autostart, symlinks, router dir, and stops proxy)
    if handler.path == "/api/ui/uninstall":
        try:
            import subprocess
            data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
            if not data.get("confirm"):
                handler.send_response(400)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "Confirmation required"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            resp = json.dumps({"status": "ok", "message": "C-Router is uninstalling..."}).encode('utf-8')
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            handler.wfile.flush()

            router_dir = os.path.dirname(os.path.abspath(__file__))
            uninstall_cmd = f"""
sleep 0.6
python3 -c '
import os, re, shutil
bashrc = os.path.expanduser("~/.bashrc")
if os.path.exists(bashrc):
    with open(bashrc, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    text = re.sub(r"\\n?# >>> crouter-autostart >>>.*?# <<< crouter-autostart <<<\\n?", "\\n", text, flags=re.S)
    text = re.sub(r"\\n?# Auto-start crouter background service if not running\\nif \\[ -x \\"\\$HOME/\\.local/bin/crouter\\" \\].*?fi\\n?", "\\n", text, flags=re.S)
    with open(bashrc, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\\n")
for d in [os.environ.get("PREFIX", "") + "/bin", os.path.expanduser("~/.local/bin"), "/data/user/0/ai.antigem/files/usr/bin", "/data/user/0/ai.antigem/files/home/.local/bin"]:
    for name in ("crouter", "croute"):
        p = os.path.join(d, name)
        if os.path.lexists(p):
            try: os.remove(p)
            except Exception: pass
shutil.rmtree({json.dumps(router_dir)}, ignore_errors=True)
'
pkill -f "proxy_v2.py" 2>/dev/null || true
"""
            subprocess.Popen(
                ["bash", "-c", uninstall_cmd],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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

        return False

    # UI API: Account Model Lock endpoints
    if handler.path == "/api/ui/account-lock":
        import account_lock_api
        return account_lock_api.handle_account_lock_post(handler, raw_body)

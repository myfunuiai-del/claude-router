#!/usr/bin/env python3
# proxy_v2.ui_tester-1.py - Model pinging, key testing, provider mode toggle, and live telemetry actions
# Modularized per gemini.md Rule 2 (Limit 400-500 lines)

import os
import sys
import json
import time
import urllib.request
import urllib.error
import importlib.util
from concurrent.futures import ThreadPoolExecutor, as_completed

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
_anthropic_mod = _load_module_to_globals("proxy_v2.transform_anthropic-1.py", globals())

def handle_ui_tester_post(handler, raw_body):
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
            if isinstance(custom_hdrs, str) and custom_hdrs.strip():
                try: custom_hdrs = json.loads(custom_hdrs)
                except Exception: custom_hdrs = {}
            p_wire = (p.get("wire_api") or "default").lower()
            clean_base = base_url.rstrip("/")

            universal_headers = {
                'Authorization': f'Bearer {api_key}' if api_key else '',
                'x-api-key': api_key if api_key else '',
                'anthropic-version': '2023-06-01',
                'Originator': 'codex_cli_rs',
                'User-Agent': 'codex_cli_rs/0.101.0' if (provider_id == 'agentrouter' or p_wire == 'responses') else 'Mozilla/5.0 (compatible; AI-Proxy/2.0)',
                'Content-Type': 'application/json',
                'Accept-Encoding': 'identity'
            }
            if custom_hdrs and isinstance(custom_hdrs, dict):
                universal_headers.update(custom_hdrs)

            # Resolve endpoint URLs
            if provider_id == "agentrouter":
                models_url = f"{clean_base}/models"
                ping_url = f"{clean_base}/messages"
            elif p_type == "openai":
                models_url = f"{clean_base}/models"
                if clean_base.endswith("/chat/completions") or clean_base.endswith("/responses") or clean_base.endswith("/messages"):
                    ping_url = clean_base
                elif p_wire == "responses" or clean_base.endswith("/v1/responses") or "/responses" in clean_base:
                    ping_url = clean_base if clean_base.endswith("/responses") else (f"{clean_base}/responses" if clean_base.endswith("/v1") else f"{clean_base}/v1/responses")
                else:
                    ping_url = f"{clean_base}/chat/completions"
            else:
                if clean_base.endswith("/api"):
                    models_url = f"{clean_base}/v1/models"
                    ping_url = f"{clean_base}/v1/messages"
                elif clean_base.endswith("/v1") or clean_base.endswith("/api/v1"):
                    models_url = f"{clean_base}/models"
                    ping_url = f"{clean_base}/messages"
                else:
                    models_url = f"{clean_base}/v1/models"
                    ping_url = f"{clean_base}/v1/messages"

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

            if isinstance(custom_hdrs, str) and custom_hdrs.strip():
                try: custom_hdrs = json.loads(custom_hdrs)
                except Exception: custom_hdrs = {}
            p_wire = (p.get("wire_api") or "default").lower()
            clean_base = base_url.rstrip("/")

            universal_headers = {
                'Authorization': f'Bearer {api_key}',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'Originator': 'codex_cli_rs',
                'User-Agent': 'codex_cli_rs/0.101.0' if (provider_id == 'agentrouter' or p_wire == 'responses') else 'Mozilla/5.0 (compatible; AI-Proxy/2.0)',
                'Content-Type': 'application/json',
                'Accept-Encoding': 'identity'
            }
            if custom_hdrs and isinstance(custom_hdrs, dict):
                universal_headers.update(custom_hdrs)

            if provider_id == "agentrouter":
                ping_url = f"{clean_base}/messages"
            elif p_type == "openai":
                if clean_base.endswith("/chat/completions") or clean_base.endswith("/responses") or clean_base.endswith("/messages"):
                    ping_url = clean_base
                elif p_wire == "responses" or clean_base.endswith("/v1/responses") or "/responses" in clean_base:
                    ping_url = clean_base if clean_base.endswith("/responses") else (f"{clean_base}/responses" if clean_base.endswith("/v1") else f"{clean_base}/v1/responses")
                else:
                    ping_url = f"{clean_base}/chat/completions"
            else:
                if clean_base.endswith("/api"):
                    ping_url = f"{clean_base}/v1/messages"
                elif clean_base.endswith("/v1") or clean_base.endswith("/api/v1"):
                    ping_url = f"{clean_base}/messages"
                else:
                    ping_url = f"{clean_base}/v1/messages"

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


    # UI API: Auto detect rate limits from server response headers
    if handler.path == "/api/ui/detect-limits":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            provider_id = (data.get("id") or data.get("provider") or "").strip().lower()
            base_url = (data.get("base_url") or "").strip()
            p_type = (data.get("type") or "openai").strip().lower()
            p_wire = (data.get("wire_api") or "default").strip().lower()
            test_model = (data.get("default_model") or data.get("model") or "").strip()
            api_key = (data.get("key") or "").strip()
            custom_hdrs = data.get("custom_headers")

            cfg = load_proxy_config()
            p = cfg.get("providers", {}).get(provider_id, {})
            if not base_url:
                base_url = p.get("base_url", "")
            if not p_type:
                p_type = p.get("type", "openai")
            if not test_model:
                test_model = p.get("default_model") or (p.get("models", [""])[0] if p.get("models") else "")
            if not api_key:
                keys = p.get("keys", [])
                api_key = keys[0] if keys else ""

            if isinstance(custom_hdrs, str) and custom_hdrs.strip():
                try:
                    custom_hdrs = json.loads(custom_hdrs)
                except Exception:
                    custom_hdrs = None
            if not custom_hdrs and p.get("custom_headers"):
                custom_hdrs = p.get("custom_headers")

            clean_base = (base_url or "").rstrip("/")
            if not clean_base or not api_key:
                handler.send_response(400)
                handler.send_header('Content-Type', 'application/json')
                handler.send_header('Access-Control-Allow-Origin', '*')
                err = json.dumps({"status": "error", "message": "Base URL and API Key are required to detect limits"}).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            universal_headers = {
                'Authorization': f'Bearer {api_key}',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            if custom_hdrs and isinstance(custom_hdrs, dict):
                universal_headers.update(custom_hdrs)

            if provider_id == "agentrouter":
                ping_url = f"{clean_base}/messages"
            elif p_type == "openai":
                if clean_base.endswith("/chat/completions") or clean_base.endswith("/responses") or clean_base.endswith("/messages"):
                    ping_url = clean_base
                elif p_wire == "responses" or clean_base.endswith("/v1/responses") or "/responses" in clean_base:
                    ping_url = clean_base if clean_base.endswith("/responses") else (f"{clean_base}/responses" if clean_base.endswith("/v1") else f"{clean_base}/v1/responses")
                else:
                    ping_url = f"{clean_base}/chat/completions"
            else:
                if clean_base.endswith("/api"):
                    ping_url = f"{clean_base}/v1/messages"
                elif clean_base.endswith("/v1") or clean_base.endswith("/api/v1"):
                    ping_url = f"{clean_base}/messages"
                else:
                    ping_url = f"{clean_base}/v1/messages"

            is_coarena = "coarena" in provider_id.lower() or "coarena.ai" in base_url
            max_tokens = 4096 if is_coarena else 2
            body = json.dumps({
                'model': test_model or 'gpt-4o',
                'messages': [{'role': 'user', 'content': 'hi'}],
                'max_tokens': max_tokens
            }).encode('utf-8')

            resp_headers = {}
            status_code = 0
            try:
                t_req = urllib.request.Request(ping_url, data=body, headers=universal_headers, method='POST')
                with urllib.request.urlopen(t_req, timeout=30) as t_resp:
                    status_code = t_resp.status
                    for k, v in t_resp.headers.items():
                        resp_headers[k.lower()] = v
            except urllib.error.HTTPError as he:
                status_code = he.code
                for k, v in he.headers.items():
                    resp_headers[k.lower()] = v
            except Exception as ex:
                status_code = 0

            rpm = None
            max_requests = None
            window_hours = 1
            tpm = None

            # 1. Mistral headers:
            # x-ratelimit-limit-req-minute => Requests Per Minute (RPM)
            # x-ratelimit-limit-tokens-minute => TPM
            if 'x-ratelimit-limit-req-minute' in resp_headers:
                try:
                    rpm = int(resp_headers['x-ratelimit-limit-req-minute'])
                except: pass
            if 'x-ratelimit-limit-tokens-minute' in resp_headers:
                try:
                    tpm = int(resp_headers['x-ratelimit-limit-tokens-minute'])
                except: pass

            # 2. Groq headers:
            # In Groq, x-ratelimit-limit-requests is Requests Per Day (RPD), NOT RPM!
            # Groq indicates reset time via x-ratelimit-reset-requests
            is_groq = "groq" in clean_base or provider_id == "groq"
            if is_groq:
                if 'x-ratelimit-limit-requests' in resp_headers:
                    try:
                        max_requests = int(resp_headers['x-ratelimit-limit-requests'])
                        window_hours = 24
                    except: pass
            else:
                # Standard OpenAI: x-ratelimit-limit-requests is RPM
                if rpm is None and 'x-ratelimit-limit-requests' in resp_headers:
                    try:
                        rpm = int(resp_headers['x-ratelimit-limit-requests'])
                    except: pass

            # 3. Explicit Daily quota header:
            if 'x-ratelimit-limit-requests-day' in resp_headers:
                try:
                    max_requests = int(resp_headers['x-ratelimit-limit-requests-day'])
                    window_hours = 24
                except: pass

            # 4. Token headers:
            if tpm is None and 'x-ratelimit-limit-tokens' in resp_headers:
                try:
                    tpm = int(resp_headers['x-ratelimit-limit-tokens'])
                except: pass

            # 5. Anthropic style headers:
            if rpm is None and 'anthropic-ratelimit-requests-limit' in resp_headers:
                try:
                    rpm = int(resp_headers['anthropic-ratelimit-requests-limit'])
                except: pass
            if tpm is None and 'anthropic-ratelimit-tokens-limit' in resp_headers:
                try:
                    tpm = int(resp_headers['anthropic-ratelimit-tokens-limit'])
                except: pass

            # 6. OpenRouter live API query (/auth/key):
            # Only extracts the actual limit returned by their API without any assumptions
            if ("openrouter" in clean_base or provider_id == "openrouter") and max_requests is None:
                try:
                    or_req = urllib.request.Request(
                        "https://openrouter.ai/api/v1/auth/key",
                        headers={"Authorization": f"Bearer {api_key}"}
                    )
                    with urllib.request.urlopen(or_req, timeout=10) as or_resp:
                        or_data = json.loads(or_resp.read().decode('utf-8')).get("data", {})
                        f_limits = or_data.get("free_model_daily_requests", {})
                        if f_limits and f_limits.get("limit"):
                            max_requests = int(f_limits["limit"])
                            window_hours = 24
                except Exception:
                    pass

            success = (rpm is not None or max_requests is not None or tpm is not None)
            resp = json.dumps({
                "status": "ok" if success else "warning",
                "detected": success,
                "rpm": rpm,
                "max_requests": max_requests,
                "window_hours": window_hours,
                "tpm": tpm,
                "http_status": status_code,
                "message": f"Detected: {rpm or '∞'} RPM, {max_requests or '∞'} Req/{window_hours}h" if success else "No rate limit headers found in server response."
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


    if handler.path == "/api/ui/provider-mode":
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

            requested_mode = (data.get("mode") or "").strip().lower()
            current_mode = (p.get("mode") or "agentic").lower()
            if requested_mode in ("agentic", "normal"):
                new_mode = requested_mode
            else:
                new_mode = "normal" if current_mode == "agentic" else "agentic"

            p["mode"] = new_mode
            save_proxy_config(cfg)
            mode_label = "⚡ Agentic (Full Tools)" if new_mode == "agentic" else "💡 Normal (Saves tokens)"
            resp = json.dumps({
                "status": "ok",
                "provider": p_id,
                "mode": new_mode,
                "message": f"{p.get('name', p_id)} switched to {mode_label}",
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
        cfg = load_proxy_config() if "load_proxy_config" in globals() else {}
        target_p = None
        for pid in cfg.get("providers", {}):
            if f"/{pid}" in handler.path:
                target_p = pid
                break
        p_info = cfg.get("providers", {}).get(target_p, {}) if target_p else {}
        p_mode = (p_info.get("mode") or "agentic").lower()
        est = 0
        try:
            b_obj = json.loads(raw_body.decode('utf-8'))
            if p_mode == "normal":
                if "apply_engine_mode_to_anthropic_body" in globals():
                    b_obj = apply_engine_mode_to_anthropic_body(b_obj, mode="normal")
            trimmed_bytes = json.dumps(b_obj, ensure_ascii=False).encode('utf-8')
            est = max(1, len(trimmed_bytes) // 4)
            # If responses wire API (e.g. Codex/Xingchi), add upstream internal instruction base
            p_wire = (p_info.get("wire_api") or "").lower()
            if p_wire == "responses":
                est += 4380
        except Exception:
            est = max(1, len(raw_body) // 4)

        resp_data = json.dumps({"input_tokens": est}).encode('utf-8')
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Content-Length', str(len(resp_data)))
        handler.end_headers()
        handler.wfile.write(resp_data)
        return True


    return False

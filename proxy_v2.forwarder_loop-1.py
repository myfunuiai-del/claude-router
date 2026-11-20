#!/usr/bin/env python3
import os
import sys
import json
import gzip
import time
import threading
import urllib.request
import urllib.error
import importlib.util

# Dynamic loader for neighbor modules
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
_transform_mod = _load_module_to_globals("proxy_v2.transform-1.py", globals())
_multi_agent_mod = _load_module_to_globals("proxy_v2.multi_agent-1.py", globals())
_balancer_mod = _load_module_to_globals("proxy_v2.key_balancer-1.py", globals())
_coarena_mod = _load_module_to_globals("proxy_v2.forwarder_coarena-1.py", globals())

def _inject_custom_prompt(body_obj, custom_prompt):
    """Prepend provider-level custom system instructions cleanly to an Anthropic request body copy."""
    if not body_obj or not isinstance(body_obj, dict):
        return body_obj
    cp = (custom_prompt or "").strip()
    if not cp:
        return body_obj
    b = dict(body_obj)
    sys_val = b.get("system")
    if isinstance(sys_val, str):
        b["system"] = f"{cp}\n\n{sys_val}" if sys_val.strip() else cp
    elif isinstance(sys_val, list):
        b["system"] = [{"type": "text", "text": cp}] + list(sys_val)
    else:
        b["system"] = cp
    return b

def _record_winner_usage(handler, p_id, p_name, model, key_label, resp_bytes, req_t0, key=None):
    in_tok, out_tok = extract_anthropic_usage(resp_bytes)
    elapsed_ms = max(1, int((time.time() - req_t0) * 1000))
    tps = round(out_tok / (elapsed_ms / 1000.0), 1) if (out_tok > 0 and elapsed_ms > 50) else 0.0
    handler._winner_info = {
        "provider": p_id,
        "provider_name": p_name,
        "model": model,
        "key_label": key_label,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "tok_per_sec": tps,
        "latency_ms": elapsed_ms
    }
    save_active_state(p_name, model, key_label, input_tokens=in_tok, output_tokens=out_tok, tok_per_sec=tps, latency_ms=elapsed_ms)
    if key and "record_key_usage" in globals():
        try:
            record_key_usage(p_id, key, in_tok, out_tok)
        except Exception:
            pass

_PROVIDER_KEY_IDX = {}

def _get_start_key_idx(p_id, n):
    return _PROVIDER_KEY_IDX.get(p_id, 0) % n if n > 0 else 0

def _advance_key_idx(p_id, idx, n, on_error=False):
    if n > 0:
        _PROVIDER_KEY_IDX[p_id] = (idx + 1) % n if on_error else (idx % n)

def _select_available_keys(p_id, keys, model=None, start_idx=None, max_count=None):
    """Return ordered [(orig_idx, key)] using sliding 60s TPM/RPM load balancer & cooldown priority.
    If all keys are in cooldown, returns all keys in balanced order so provider never hard-locks.
    """
    if not keys:
        return []
    if "select_balanced_keys_ordered" in globals():
        cooldown_fn = globals().get("is_key_in_cooldown")
        chosen = select_balanced_keys_ordered(p_id, keys, model=model, is_cooldown_fn=cooldown_fn)
    else:
        n = len(keys)
        start = (start_idx or 0) % n
        rotated = [((start + i) % n, keys[(start + i) % n]) for i in range(n)]
        ready = [(idx, k) for idx, k in rotated if globals().get("is_key_in_cooldown", lambda *_: 0)(p_id, k, model) == 0]
        chosen = ready if ready else rotated
    if max_count is not None:
        chosen = chosen[:max_count]
    return chosen

def try_forward_provider(handler, p_id, raw_body, body_obj, orig_model, is_recovery=False, allow_model_fallback=True):
    """Attempts to forward the request to provider p_id.
    Returns True if successful and response was written to client, False if failed/exhausted.
    """
    global current_coarena_idx, current_openrouter_idx, current_groq_idx, current_gonka_idx
    global fallback_to_agentrouter, last_fallback_time
    handler._last_http_error = None
    cfg = load_proxy_config()
    all_providers = cfg.get("providers", {})
    p_info = all_providers.get(p_id, {})

    if p_info.get("enabled", True) is False:
        sys.stderr.write(f"[Proxy] Provider '{p_id}' is OFF (disabled). Skipping.\n")
        return False

    # Inject provider-level custom system prompt if configured
    custom_prompt = (p_info.get("custom_prompt") or "").strip()
    if custom_prompt and body_obj is not None:
        body_obj = _inject_custom_prompt(body_obj, custom_prompt)

    if p_id == "coarena":
        return forward_coarena(handler, raw_body, body_obj, orig_model, is_recovery, allow_model_fallback, p_info, all_providers, globals())

    elif p_id == "agentrouter":
        ar_keys = p_info.get("keys") or [get_agentrouter_key()]
        ar_model = p_info.get("default_model", "gpt-5.6-sol")
        ar_base = p_info.get("base_url", "https://agentrouter.org/v1").rstrip("/")
        ar_url = f"{ar_base}/messages"

        ar_candidates = _select_available_keys("agentrouter", ar_keys, ar_model, max_count=(2 if is_recovery else None))
        for attempt, key in ar_candidates:
            req_id = getattr(handler, "_live_req_id", None)
            stage_lbl = getattr(handler, "_live_stage", "Original")
            if req_id:
                set_in_flight(req_id, "agentrouter", p_info.get("name", "AgentRouter"), ar_model, f"Key #{attempt+1}", stage_lbl, handler.path)
            if body_obj is not None:
                b_copy = dict(body_obj)
                b_copy['model'] = ar_model
                if 'tools' in b_copy: del b_copy['tools']
                if 'tool_choice' in b_copy: del b_copy['tool_choice']
                if 'thinking' in b_copy: del b_copy['thinking']
                ar_body = json.dumps(b_copy).encode('utf-8')
            else:
                ar_body = raw_body

            ar_headers = {
                'Authorization': f"Bearer {key}",
                'User-Agent': 'codex_cli_rs/0.101.0',
                'Originator': 'codex_cli_rs',
                'Content-Type': 'application/json',
                'Accept-Encoding': 'identity'
            }
            req = urllib.request.Request(ar_url, data=ar_body, headers=ar_headers, method='POST')
            req_t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp_data = resp.read()
                    clear_key_cooldown("agentrouter", key, ar_model)
                    p_name = p_info.get("name", "AgentRouter")
                    _record_winner_usage(handler, "agentrouter", p_name, ar_model, f"Key #{attempt+1}", resp_data, req_t0, key=key)
                    resp_data = append_signature_to_response(resp_data, p_name, ar_model)
                    handler.send_response(resp.status)
                    for k, val in resp.headers.items():
                        if k.lower() not in ['transfer-encoding', 'content-encoding', 'content-length', 'connection']:
                            handler.send_header(k, val)
                    handler.send_header('Content-Length', str(len(resp_data)))
                    handler.end_headers()
                    handler.wfile.write(resp_data)
                    return True
            except urllib.error.HTTPError as e:
                handler._last_http_error = e.code
                try:
                    err_txt = e.read().decode('utf-8', errors='ignore')[:200]
                except Exception:
                    err_txt = ""
                mark_key_cooldown("agentrouter", key, e.code, ar_model, err_txt)
                record_live_issue("agentrouter", p_info.get("name", "AgentRouter"), ar_model, f"Key #{attempt+1}", e.code, err_txt)
                sys.stderr.write(f"[Proxy] AgentRouter attempt #{attempt+1} HTTP error {e.code}\n")
                if e.code in (400, 413):
                    return False
                continue
            except Exception as e:
                record_live_issue("agentrouter", p_info.get("name", "AgentRouter"), ar_model, f"Key #{attempt+1}", 0, str(e))
                sys.stderr.write(f"[Proxy] AgentRouter attempt #{attempt+1} error: {e}\n")
                continue
        return False

    elif p_id in all_providers:
        p_keys = p_info.get("keys", [])
        if not p_keys:
            return False
        p_base = p_info.get("base_url", "").rstrip("/")
        p_type = p_info.get("type", "anthropic")
        p_models = p_info.get("models", [])
        p_def_model = p_info.get("default_model", orig_model)

        clean_orig = orig_model
        if clean_orig.startswith(f"@{p_id}/"):
            clean_orig = clean_orig[len(f"@{p_id}/"):]
        elif clean_orig.startswith("@") and "/" in clean_orig:
            clean_orig = clean_orig.split("/", 1)[1]

        # Build prioritized list of model candidates for this server
        matched_model = None
        c_tail = clean_orig.split("/")[-1].split(":")[0].lower()
        if clean_orig in p_models:
            matched_model = clean_orig
        else:
            for m in p_models:
                if c_tail == m.split("/")[-1].split(":")[0].lower():
                    matched_model = m
                    break
        if not matched_model and p_def_model:
            if c_tail == p_def_model.split("/")[-1].split(":")[0].lower():
                matched_model = p_def_model

        if not allow_model_fallback:
            if matched_model:
                candidates = [matched_model]
            elif not p_models:
                candidates = [clean_orig]
            else:
                return False
        else:
            primary_model = matched_model or p_def_model or clean_orig
            candidates = [primary_model]
            if not is_recovery:
                if p_def_model and p_def_model not in candidates:
                    candidates.append(p_def_model)
                for m in p_models:
                    if m not in candidates:
                        candidates.append(m)

        p_mode = p_info.get("mode", "agentic")
        for model_idx, target_model in enumerate(candidates):
            if model_idx > 0:
                sys.stderr.write(f"[Proxy] Fallback to next model '{target_model}' (#{model_idx+1}/{len(candidates)}) on '{p_id}'...\n")

            if p_type == "anthropic":
                fwd_url = f"{p_base}/v1/messages" if p_base.endswith("/api") else f"{p_base}/messages"
                if body_obj is not None:
                    b_copy = apply_engine_mode_to_anthropic_body(body_obj, p_mode)
                    b_copy['model'] = target_model
                    if p_id == "openrouter" and isinstance(b_copy.get('max_tokens'), int) and b_copy['max_tokens'] > 2048:
                        b_copy['max_tokens'] = 2048
                    fwd_body = json.dumps(b_copy).encode('utf-8')
                else:
                    fwd_body = raw_body

                p_candidates = _select_available_keys(p_id, p_keys, target_model, max_count=(2 if is_recovery else None))
                for attempt, key in p_candidates:
                    req_id = getattr(handler, "_live_req_id", None)
                    stage_lbl = getattr(handler, "_live_stage", "Original")
                    if req_id:
                        set_in_flight(req_id, p_id, p_info.get("name", p_id), target_model, f"Key #{attempt+1}", stage_lbl, handler.path)
                    fwd_headers = {
                        'Authorization': f"Bearer {key}",
                        'x-api-key': key,
                        'anthropic-version': '2023-06-01',
                        'Originator': 'codex_cli_rs',
                        'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0 (compatible; AI-Proxy/2.0)',
                        'Accept-Encoding': 'identity'
                    }
                    custom_hdrs = p_info.get("custom_headers")
                    if custom_hdrs and isinstance(custom_hdrs, dict):
                        fwd_headers.update(custom_hdrs)
                    req = urllib.request.Request(fwd_url, data=fwd_body, headers=fwd_headers, method='POST')
                    req_t0 = time.time()
                    try:
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            resp_data = resp.read()
                            _advance_key_idx(p_id, attempt, len(p_keys), on_error=False)
                            clear_key_cooldown(p_id, key, target_model)
                            p_name = p_info.get("name", p_id)
                            _record_winner_usage(handler, p_id, p_name, target_model, f"Key #{attempt+1}", resp_data, req_t0, key=key)
                            resp_data = append_signature_to_response(resp_data, p_name, target_model)
                            handler.send_response(resp.status)
                            for k, val in resp.headers.items():
                                if k.lower() not in ['transfer-encoding', 'content-encoding', 'content-length', 'connection']:
                                    handler.send_header(k, val)
                            handler.send_header('Content-Length', str(len(resp_data)))
                            handler.end_headers()
                            handler.wfile.write(resp_data)
                            return True
                    except urllib.error.HTTPError as e:
                        handler._last_http_error = e.code
                        try:
                            err_txt = e.read().decode('utf-8', errors='ignore')[:200]
                        except Exception:
                            err_txt = ""
                        if e.code in (401, 402, 429):
                            _advance_key_idx(p_id, attempt, len(p_keys), on_error=True)
                        mark_key_cooldown(p_id, key, e.code, target_model, err_txt)
                        record_live_issue(p_id, p_info.get("name", p_id), target_model, f"Key #{attempt+1}", e.code, err_txt)
                        if e.code == 429:
                            sys.stderr.write(f"[Proxy Auto-Retry] {p_id} ({target_model}) Key #{attempt+1} hit 429/Quota! Instantly switching to next key...\n")
                        else:
                            sys.stderr.write(f"[Proxy] {p_id} ({target_model}) key #{attempt+1} HTTP error {e.code}. Trying next key...\n")
                        if e.code == 413 or (e.code == 400 and any(tok in err_txt.lower() for tok in ("too long", "token", "context", "length"))):
                            return False
                        if e.code == 400:
                            break
                        continue
                    except Exception as e:
                        record_live_issue(p_id, p_info.get("name", p_id), target_model, f"Key #{attempt+1}", 0, str(e))
                        sys.stderr.write(f"[Proxy] {p_id} ({target_model}) key #{attempt+1} error: {e}\n")
                        continue

            elif p_type == "openai":
                is_stream = body_obj.get("stream", False) if body_obj else False
                openai_body_obj = anthropic_to_openai_body(body_obj, target_model, p_id=p_id, mode=p_mode, base_url=p_base) if body_obj else {}
                fwd_body = json.dumps(openai_body_obj, ensure_ascii=False).encode('utf-8')
                
                # Smart Foolproof URL resolution
                p_wire = (p_info.get("wire_api") or "default").lower()
                clean_base = p_base.rstrip("/")
                if clean_base.endswith("/chat/completions") or clean_base.endswith("/responses") or clean_base.endswith("/messages"):
                    fwd_url = clean_base
                elif p_wire == "responses" or clean_base.endswith("/v1/responses") or "/responses" in clean_base:
                    fwd_url = clean_base if clean_base.endswith("/responses") else (f"{clean_base}/responses" if clean_base.endswith("/v1") else f"{clean_base}/v1/responses")
                else:
                    fwd_url = f"{clean_base}/chat/completions"

                p_candidates = _select_available_keys(p_id, p_keys, target_model, max_count=(2 if is_recovery else None))
                for attempt, key in p_candidates:
                    req_id = getattr(handler, "_live_req_id", None)
                    stage_lbl = getattr(handler, "_live_stage", "Original")
                    if req_id:
                        set_in_flight(req_id, p_id, p_info.get("name", p_id), target_model, f"Key #{attempt+1}", stage_lbl, handler.path)
                    fwd_headers = {
                        'Authorization': f"Bearer {key}",
                        'Content-Type': 'application/json',
                        'User-Agent': 'codex_cli_rs/0.101.0' if (p_wire == 'responses' or p_id == 'agentrouter') else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                        'Accept-Encoding': 'identity'
                    }
                    custom_hdrs = p_info.get("custom_headers")
                    if isinstance(custom_hdrs, str) and custom_hdrs.strip():
                        try: custom_hdrs = json.loads(custom_hdrs)
                        except Exception: custom_hdrs = {}
                    if custom_hdrs and isinstance(custom_hdrs, dict):
                        fwd_headers.update(custom_hdrs)
                    req = urllib.request.Request(fwd_url, data=fwd_body, headers=fwd_headers, method='POST')
                    req_t0 = time.time()
                    try:
                        with urllib.request.urlopen(req, timeout=90) as resp:
                            resp_data = resp.read()
                            _advance_key_idx(p_id, attempt, len(p_keys), on_error=False)
                            clear_key_cooldown(p_id, key, target_model)
                            p_name = p_info.get("name", p_id)
                            text = resp_data.decode('utf-8', errors='ignore')
                            if is_stream or "data:" in text or "event:" in text:
                                anth_resp = convert_openai_stream_to_anthropic(text, p_name, target_model)
                                _record_winner_usage(handler, p_id, p_name, target_model, f"Key #{attempt+1}", anth_resp, req_t0, key=key)
                                handler.send_response(200)
                                handler.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                                handler.send_header('Content-Length', str(len(anth_resp)))
                                handler.end_headers()
                                handler.wfile.write(anth_resp)
                                return True
                            else:
                                try:
                                    o_json = json.loads(text)
                                    anth_resp = convert_openai_json_to_anthropic(o_json, p_name, target_model)
                                    _record_winner_usage(handler, p_id, p_name, target_model, f"Key #{attempt+1}", anth_resp, req_t0, key=key)
                                    handler.send_response(200)
                                    handler.send_header('Content-Type', 'application/json')
                                    handler.send_header('Content-Length', str(len(anth_resp)))
                                    handler.end_headers()
                                    handler.wfile.write(anth_resp)
                                    return True
                                except Exception:
                                    pass
                            _record_winner_usage(handler, p_id, p_name, target_model, f"Key #{attempt+1}", resp_data, req_t0, key=key)
                            handler.send_response(resp.status)
                            handler.send_header('Content-Length', str(len(resp_data)))
                            handler.end_headers()
                            handler.wfile.write(resp_data)
                            return True
                    except urllib.error.HTTPError as e:
                        handler._last_http_error = e.code
                        try:
                            err_txt = e.read().decode('utf-8', errors='ignore')[:200]
                        except Exception:
                            err_txt = ""
                        if e.code in (401, 402, 429):
                            _advance_key_idx(p_id, attempt, len(p_keys), on_error=True)
                        mark_key_cooldown(p_id, key, e.code, target_model, err_txt)
                        record_live_issue(p_id, p_info.get("name", p_id), target_model, f"Key #{attempt+1}", e.code, err_txt)
                        if e.code == 429:
                            sys.stderr.write(f"[Proxy Auto-Retry] {p_id} ({target_model}) Key #{attempt+1} hit 429/Quota! Instantly switching to next key...\n")
                        else:
                            sys.stderr.write(f"[Proxy] {p_id} ({target_model}) key #{attempt+1} HTTP error {e.code}. Trying next key...\n")
                        if e.code == 413 or (e.code == 400 and any(tok in err_txt.lower() for tok in ("too long", "token", "context", "length"))):
                            return False
                        if e.code == 400:
                            break
                        continue
                    except Exception as e:
                        record_live_issue(p_id, p_info.get("name", p_id), target_model, f"Key #{attempt+1}", 0, str(e))
                        sys.stderr.write(f"[Proxy] {p_id} ({target_model}) key #{attempt+1} error: {e}\n")
                        continue

        return False

    return False


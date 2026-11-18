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

def _record_winner_usage(handler, p_id, p_name, model, key_label, resp_bytes, req_t0):
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

_PROVIDER_KEY_IDX = {}

def _get_start_key_idx(p_id, n):
    if n <= 0:
        return 0
    return _PROVIDER_KEY_IDX.get(p_id, 0) % n

def _advance_key_idx(p_id, idx, n, on_error=False):
    if n <= 0:
        return
    _PROVIDER_KEY_IDX[p_id] = (idx + 1) % n if on_error else (idx % n)

def _select_available_keys(p_id, keys, model=None, start_idx=None, max_count=None):
    """Return rotated [(orig_idx, key)] starting from last healthy key, skipping keys in cooldown.
    If every key is in cooldown, falls back to returning all rotated keys so provider never hard-locks.
    """
    n = len(keys)
    if n == 0:
        return []
    if start_idx is None:
        start_idx = _get_start_key_idx(p_id, n)
    rotated = [((start_idx + i) % n, keys[(start_idx + i) % n]) for i in range(n)]
    ready = [(idx, k) for idx, k in rotated if is_key_in_cooldown(p_id, k, model) == 0]
    chosen = ready if ready else rotated
    if max_count is not None:
        chosen = chosen[:max_count]
    return chosen

def try_forward_provider(handler, p_id, raw_body, body_obj, orig_model, is_recovery=False):
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
        candidates = [orig_model]
        if orig_model in MODEL_FALLBACKS:
            candidates.extend(MODEL_FALLBACKS[orig_model])
        coa_def = p_info.get("default_model", "gemini-4-carbon")
        if coa_def not in candidates:
            candidates.append(coa_def)
        if is_recovery:
            candidates = candidates[:1]

        target_path = handler.path
        for known_pid in all_providers:
            pfx = f"/{known_pid}"
            if target_path == pfx or target_path.startswith(f"{pfx}/") or target_path.startswith(f"{pfx}?"):
                target_path = target_path[len(pfx):] or "/v1/messages"
                break
        if not target_path.startswith('/api'):
            target_path = '/api' + target_path
        elif target_path.startswith('/api/api'):
            target_path = target_path[4:]
        upstream_url = "https://coarena.ai" + target_path

        coarena_keys = p_info.get("keys") or get_coarena_keys()
        if not coarena_keys:
            return False
        max_key_attempts = min(2, len(coarena_keys)) if is_recovery else len(coarena_keys)

        p_mode = p_info.get("mode", "agentic")
        for model_to_try in candidates:
            coarena_model = model_to_try
            if body_obj is not None:
                b_copy = apply_engine_mode_to_anthropic_body(body_obj, p_mode)
                b_copy['model'] = coarena_model
                if 'max_tokens' in b_copy and isinstance(b_copy['max_tokens'], int):
                    if b_copy['max_tokens'] < 4096:
                        b_copy['max_tokens'] = 4096
                body = json.dumps(b_copy).encode('utf-8')
            else:
                body = raw_body

            key_candidates = _select_available_keys("coarena", coarena_keys, coarena_model, start_idx=current_coarena_idx, max_count=max_key_attempts)
            for idx, key in key_candidates:
                req_id = getattr(handler, "_live_req_id", None)
                stage_lbl = getattr(handler, "_live_stage", "Original")
                if req_id:
                    set_in_flight(req_id, "coarena", p_info.get("name", "Coarena"), coarena_model, f"Key #{idx+1}", stage_lbl, handler.path)
                req_headers = {}
                for h, v in handler.headers.items():
                    if h.lower() not in ['host', 'content-length', 'authorization', 'x-api-key', 'accept-encoding']:
                        req_headers[h] = v
                req_headers['Accept-Encoding'] = 'identity'
                req_headers['Authorization'] = f"Bearer {key}"
                req_headers['x-api-key'] = key

                req = urllib.request.Request(upstream_url, data=body, headers=req_headers, method='POST')
                req_t0 = time.time()
                try:
                    with urllib.request.urlopen(req, timeout=35) as resp:
                        resp_data = resp.read()
                        if resp.headers.get('Content-Encoding', '').lower() == 'gzip':
                            try:
                                resp_data = gzip.decompress(resp_data)
                            except Exception:
                                pass
                        current_coarena_idx = idx
                        clear_key_cooldown("coarena", key, coarena_model)
                        p_name = p_info.get("name", "Coarena")
                        _record_winner_usage(handler, "coarena", p_name, coarena_model, f"Key #{idx+1}", resp_data, req_t0)
                        resp_data = append_signature_to_response(resp_data, p_name, coarena_model)
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
                    err_body = ""
                    try:
                        err_body = e.read().decode('utf-8', errors='ignore')
                    except Exception:
                        pass
                    mark_key_cooldown("coarena", key, e.code, coarena_model, err_body)
                    record_live_issue("coarena", p_info.get("name", "Coarena"), coarena_model, f"Key #{idx+1}", e.code, err_body[:200])
                    sys.stderr.write(f"[Proxy] Coarena key #{idx+1} HTTP error {e.code}: {err_body[:300]}. URL: {upstream_url}. Model: {coarena_model}.\n")
                    if e.code in (400, 413):
                        err_low = err_body.lower()
                        is_model_err = ("model" in err_low) and ("not found" in err_low or "unknown model" in err_low or "invalid model" in err_low)
                        if is_model_err:
                            break  # Try next candidate model, don't waste remaining keys
                        return False  # Payload error: jump straight to Recovery instead of looping 10 keys
                    continue
                except Exception as e:
                    record_live_issue("coarena", p_info.get("name", "Coarena"), coarena_model, f"Key #{idx+1}", 0, str(e))
                    sys.stderr.write(f"[Proxy] Coarena key #{idx+1} network error: {e}. Trying next...\n")
                    continue
        return False

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
                    _record_winner_usage(handler, "agentrouter", p_name, ar_model, f"Key #{attempt+1}", resp_data, req_t0)
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
                err_txt = ""
                try:
                    err_txt = e.read().decode('utf-8', errors='ignore')[:200]
                except Exception:
                    pass
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
        if clean_orig in p_models:
            matched_model = clean_orig
        else:
            c_tail = clean_orig.split("/")[-1]
            for m in p_models:
                if c_tail == m.split("/")[-1]:
                    matched_model = m
                    break

        primary_model = matched_model or p_def_model or clean_orig
        candidates = [primary_model]
        if not is_recovery:
            # During normal routing, sequentially try all models configured for this provider if primary fails
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
                            _record_winner_usage(handler, p_id, p_name, target_model, f"Key #{attempt+1}", resp_data, req_t0)
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
                        err_txt = ""
                        try:
                            err_txt = e.read().decode('utf-8', errors='ignore')[:200]
                        except Exception:
                            pass
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
                fwd_url = p_base if p_base.endswith("/chat/completions") else f"{p_base}/chat/completions"

                p_candidates = _select_available_keys(p_id, p_keys, target_model, max_count=(2 if is_recovery else None))
                for attempt, key in p_candidates:
                    req_id = getattr(handler, "_live_req_id", None)
                    stage_lbl = getattr(handler, "_live_stage", "Original")
                    if req_id:
                        set_in_flight(req_id, p_id, p_info.get("name", p_id), target_model, f"Key #{attempt+1}", stage_lbl, handler.path)
                    fwd_headers = {
                        'Authorization': f"Bearer {key}",
                        'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                        'Accept-Encoding': 'identity'
                    }
                    custom_hdrs = p_info.get("custom_headers")
                    if custom_hdrs and isinstance(custom_hdrs, dict):
                        fwd_headers.update(custom_hdrs)
                    req = urllib.request.Request(fwd_url, data=fwd_body, headers=fwd_headers, method='POST')
                    req_t0 = time.time()
                    try:
                        with urllib.request.urlopen(req, timeout=45) as resp:
                            resp_data = resp.read()
                            _advance_key_idx(p_id, attempt, len(p_keys), on_error=False)
                            clear_key_cooldown(p_id, key, target_model)
                            p_name = p_info.get("name", p_id)
                            text = resp_data.decode('utf-8', errors='ignore')
                            if is_stream or "data:" in text:
                                anth_resp = convert_openai_stream_to_anthropic(text, p_name, target_model)
                                _record_winner_usage(handler, p_id, p_name, target_model, f"Key #{attempt+1}", anth_resp, req_t0)
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
                                    _record_winner_usage(handler, p_id, p_name, target_model, f"Key #{attempt+1}", anth_resp, req_t0)
                                    handler.send_response(200)
                                    handler.send_header('Content-Type', 'application/json')
                                    handler.send_header('Content-Length', str(len(anth_resp)))
                                    handler.end_headers()
                                    handler.wfile.write(anth_resp)
                                    return True
                                except Exception:
                                    pass
                            _record_winner_usage(handler, p_id, p_name, target_model, f"Key #{attempt+1}", resp_data, req_t0)
                            handler.send_response(resp.status)
                            handler.send_header('Content-Length', str(len(resp_data)))
                            handler.end_headers()
                            handler.wfile.write(resp_data)
                            return True
                    except urllib.error.HTTPError as e:
                        handler._last_http_error = e.code
                        err_txt = ""
                        try:
                            err_txt = e.read().decode('utf-8', errors='ignore')[:200]
                        except Exception:
                            pass
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

def route_to_agentrouter(handler, raw_body, body_obj):
    """Helper to seamlessly route to AgentRouter gpt-5.6-sol"""
    return try_forward_provider(handler, "agentrouter", raw_body, body_obj, "gpt-5.6-sol")

def _friendly_stage_label(stage_name):
    if stage_name == "shrink_old_tools_keep_last":
        return "Stage 1: Old Tools Shrunk"
    if stage_name == "shrink_all_large_blocks":
        return "Stage 2: All Large Blocks Shrunk"
    if stage_name.startswith("recent_with_context_"):
        cnt = stage_name.replace("recent_with_context_", "").replace("_msgs", "")
        return f"Stage 3: Recent {cnt} Msgs + Full Context"
    if stage_name.startswith("recent_"):
        return f"Stage 3: Recent Msgs ({stage_name.replace('recent_', '').replace('_msgs', '')})"
    if stage_name == "last_msg_with_context":
        return "Stage 4: 1 Msg + Full Chat Context"
    if stage_name in ("last_msg_bare", "last_message_only"):
        return "Stage 5: 1 Msg Bare (Fallback)"
    return stage_name

def try_forward_with_history_recovery(handler, p_id, raw_body, body_obj, orig_model):
    """Try forwarding original request to p_id. On 400/403/413 with trimmable history,
    escalate safely on the same provider without mutating original body_obj:
      1) Full history + untouched last message, shrinking only older large tool outputs
      2) Keep only recent ~6-8 messages
      3) Keep only the last message
      4) Full history + last message with all large tool outputs & text blocks shrunk
    Stage 5: If all fail, return False so caller routes untouched original request to next server.
    """
    handler._live_stage = "Original"
    if try_forward_provider(handler, p_id, raw_body, body_obj, orig_model, is_recovery=False):
        return True

    cfg = load_proxy_config()
    if cfg.get("auto_recovery", True) is False:
        return False

    last_err = getattr(handler, "_last_http_error", None)
    if last_err in (400, 403, 413) and is_trimmable_history(body_obj):
        variants = build_history_recovery_variants(body_obj)
        total = len(variants)
        for idx, (stage_name, v_body_obj) in enumerate(variants, start=1):
            pretty = _friendly_stage_label(stage_name)
            handler._live_stage = pretty
            sys.stderr.write(f"[Proxy Recovery {idx}/{total}] '{p_id}' hit HTTP {last_err}. Retrying with '{stage_name}'...\n")
            v_raw = json.dumps(v_body_obj, ensure_ascii=False).encode('utf-8')
            if try_forward_provider(handler, p_id, v_raw, v_body_obj, orig_model, is_recovery=True):
                handler._recovery_stage = pretty
                sys.stderr.write(f"[Proxy Recovery {idx}/{total}] '{p_id}' SUCCEEDED via '{stage_name}'!\n")
                return True
        if total > 0:
            sys.stderr.write(f"[Proxy Recovery] All {total} trimmed retries failed on '{p_id}'. Passing full original request to next server...\n")

    handler._live_stage = "Original"
    return False

def dispatch_inference(handler, raw_body):
    """Parses incoming request, checks dedicated direct route or dynamic pipeline failover."""
    orig_model = "unknown"
    body_obj = None
    try:
        body_obj = json.loads(raw_body.decode('utf-8'))
        orig_model = body_obj.get('model', 'unknown')
        body_obj = clean_history_tags(body_obj)
        body_obj = sanitize_anthropic_body(body_obj)
    except Exception:
        pass

    req_id = f"req_{int(time.time() * 1000)}_{threading.get_ident()}"
    t_start = time.time()
    handler._live_req_id = req_id
    handler._winner_info = None
    handler._recovery_stage = None
    handler._live_stage = "Original"
    failed_providers = []

    cfg = load_proxy_config()
    all_providers = cfg.get("providers", {})
    attempted_providers = set()

    def _finish_success():
        w = getattr(handler, "_winner_info", None) or {"provider": "unknown", "provider_name": "Unknown", "model": orig_model, "key_label": "-"}
        rec = getattr(handler, "_recovery_stage", None)
        if failed_providers and rec:
            rec_str = f"Stage 5 Failover (after {', '.join(failed_providers)}) + {rec}"
        elif failed_providers:
            rec_str = f"Stage 5: Failover (after {', '.join(failed_providers)})"
        else:
            rec_str = rec or ""
        record_live_request(
            w["provider"], w["provider_name"], w["model"], w["key_label"],
            status="ok", code=200, latency_ms=int((time.time() - t_start) * 1000),
            path=handler.path, recovery_stage=rec_str, failover_from=failed_providers,
            input_tokens=w.get("input_tokens", 0),
            output_tokens=w.get("output_tokens", 0),
            tok_per_sec=w.get("tok_per_sec", 0.0)
        )

    try:
        # 1. DEDICATED DIRECT ROUTE: Matches any provider endpoint (/{p_id} or /{p_id}/*)
        target_dedicated_provider = None
        for p_id in all_providers:
            prefix = f"/{p_id}"
            if handler.path == prefix or handler.path.startswith(f"{prefix}/") or handler.path.startswith(f"{prefix}?"):
                target_dedicated_provider = p_id
                break

        if target_dedicated_provider:
            attempted_providers.add(target_dedicated_provider)
            p_info = all_providers.get(target_dedicated_provider, {})
            p_name = p_info.get("name", target_dedicated_provider)
            sys.stderr.write(f"[Proxy Direct Route] Request targeted specifically to '{target_dedicated_provider}' (Path: {handler.path})\n")

            # try_forward_with_history_recovery already iterates sequentially through all configured models of this server
            if try_forward_with_history_recovery(handler, target_dedicated_provider, raw_body, body_obj, orig_model):
                _finish_success()
                return

            # Explicit standalone/standby server route: DO NOT cascade into active routed pipeline!
            failed_providers.append(p_name)
            last_err = getattr(handler, "_last_http_error", None) or 502
            sys.stderr.write(f"[Proxy Direct Route] Standalone dedicated provider '{target_dedicated_provider}' failed on all configured models. Strictly halting without pipeline cascade.\n")
            record_live_request(
                target_dedicated_provider, p_name, orig_model, "-", status="err", code=last_err,
                latency_ms=int((time.time() - t_start) * 1000), path=handler.path,
                recovery_stage="", failover_from=failed_providers
            )
            handler.send_response(last_err)
            handler.send_header('Content-Type', 'application/json')
            msg = json.dumps({"error": {"message": f"Server '{p_name}' ({target_dedicated_provider}) failed across its configured models and standby isolation is enforced. It did not cascade to routed pipeline."}}).encode()
            handler.send_header('Content-Length', str(len(msg)))
            handler.end_headers()
            handler.wfile.write(msg)
            return

        routed_providers = cfg.get("routed_providers", [])
        if not routed_providers:
            routed_providers = ["coarena"]

        # 1.5 SMART MODEL-TO-PROVIDER ROUTE: Only route if provider is active (in routed_providers) and enabled (ON)
        if orig_model and orig_model != "unknown":
            clean_model = orig_model.split("/")[-1] if "/" in orig_model else orig_model
            for p_id in routed_providers:
                if p_id in attempted_providers:
                    continue
                p_info = all_providers.get(p_id, {})
                if p_info.get("enabled", True) is False:
                    continue
                p_models = p_info.get("models", [])
                if orig_model in p_models or any(clean_model == m.split("/")[-1] for m in p_models):
                    attempted_providers.add(p_id)
                    sys.stderr.write(f"[Proxy Model Route] Model '{orig_model}' matched active provider '{p_id}'. Routing directly...\n")
                    if try_forward_with_history_recovery(handler, p_id, raw_body, body_obj, orig_model):
                        _finish_success()
                        return
                    failed_providers.append(p_info.get("name", p_id))
                    sys.stderr.write(f"[Proxy Model Route] Provider '{p_id}' failed for model '{orig_model}'. Falling back to pipeline...\n")
                    break

        # 2. Dynamic Priority Pipeline (routed_providers) — skips disabled (OFF) or already-tried providers
        success = False
        for prio_idx, p_id in enumerate(routed_providers):
            if p_id in attempted_providers:
                continue
            p_info = all_providers.get(p_id, {})
            if p_info.get("enabled", True) is False:
                sys.stderr.write(f"[Proxy Pipeline] [Priority #{prio_idx+1}] '{p_id}' is OFF. Skipping...\n")
                continue
            attempted_providers.add(p_id)
            sys.stderr.write(f"[Proxy Pipeline] [Priority #{prio_idx+1}] Routing to '{p_id}'...\n")
            if try_forward_with_history_recovery(handler, p_id, raw_body, body_obj, orig_model):
                success = True
                _finish_success()
                break
            failed_providers.append(p_info.get("name", p_id))
            sys.stderr.write(f"[Proxy Pipeline] [Priority #{prio_idx+1}] '{p_id}' failed. Cascading to next...\n")

        if not success:
            record_live_issue("pipeline", "Pipeline", orig_model, "-", 502, "All enabled servers failed or are turned OFF")
            record_live_request(
                "pipeline", "Pipeline", orig_model, "-", status="err", code=502,
                latency_ms=int((time.time() - t_start) * 1000), path=handler.path,
                recovery_stage="", failover_from=failed_providers
            )
            handler.send_response(502)
            handler.send_header('Content-Type', 'application/json')
            msg = json.dumps({"error": {"message": "All enabled servers in the active routed pipeline failed or are turned OFF."}}).encode()
            handler.send_header('Content-Length', str(len(msg)))
            handler.end_headers()
            handler.wfile.write(msg)
    finally:
        clear_in_flight(req_id)

#!/usr/bin/env python3
import sys
import json
import gzip
import time
import urllib.request
import urllib.error

def forward_coarena(handler, raw_body, body_obj, orig_model, is_recovery, allow_model_fallback, p_info, all_providers, globals_dict):
    """Handles forwarding requests specifically to Coarena upstream.
    Preserves exact model parity on Pass 1 (allow_model_fallback=False),
    or cascades through MODEL_FALLBACKS on Pass 2 (allow_model_fallback=True).
    """
    get_coarena_keys = globals_dict["get_coarena_keys"]
    _select_available_keys = globals_dict["_select_available_keys"]
    set_in_flight = globals_dict["set_in_flight"]
    clear_key_cooldown = globals_dict["clear_key_cooldown"]
    mark_key_cooldown = globals_dict["mark_key_cooldown"]
    _record_winner_usage = globals_dict["_record_winner_usage"]
    append_signature_to_response = globals_dict["append_signature_to_response"]
    record_live_issue = globals_dict["record_live_issue"]
    apply_engine_mode_to_anthropic_body = globals_dict["apply_engine_mode_to_anthropic_body"]
    MODEL_FALLBACKS = globals_dict.get("MODEL_FALLBACKS", {})

    _note_dispatch = globals_dict.get("_note_dispatch")
    urlopen_for_key = globals_dict.get("urlopen_for_key")
    egress_guard = globals_dict.get("egress_guard")
    _clear_attempt_cooldown = globals_dict.get("_clear_attempt_cooldown")
    _mark_attempt_cooldown = globals_dict.get("_mark_attempt_cooldown")

    coa_def = p_info.get("default_model", "gemini-4-carbon")
    coa_sup = ("gemini-4-carbon", "gemini-3-8-flash", "deepseek-v4-1-flash-1017")
    c_tail = orig_model.split("/")[-1] if "/" in orig_model else orig_model
    coa_match = orig_model if orig_model in coa_sup else (c_tail if c_tail in coa_sup else None)
    if not allow_model_fallback:
        if not coa_match:
            return False
        candidates = [coa_match]
    elif is_recovery:
        candidates = [coa_match or coa_def]
    else:
        candidates = [orig_model]
        if orig_model in MODEL_FALLBACKS:
            candidates.extend(MODEL_FALLBACKS[orig_model])
        if coa_def not in candidates:
            candidates.append(coa_def)

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
    current_coarena_idx = globals_dict.get("current_coarena_idx", 0)

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

        key_candidates = _select_available_keys("coarena", coarena_keys, coarena_model, start_idx=current_coarena_idx, max_count=max_key_attempts, p_info=p_info)
        if not key_candidates:
            handler._last_http_error = 429
            return False
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
                from contextlib import nullcontext
                guard_cm = egress_guard("coarena", p_info=p_info, key=key, key_index=idx) if egress_guard else nullcontext()
                with guard_cm:
                    if _note_dispatch:
                        _note_dispatch("coarena", key)
                    _open_cm = urlopen_for_key(req, p_info=p_info, key=key, key_index=idx, timeout=35) if urlopen_for_key else urllib.request.urlopen(req, timeout=35)
                    with _open_cm as resp:
                        resp_data = resp.read()
                        resp_status = resp.status
                        resp_hdrs = dict(resp.headers.items())
                        resp_enc = resp.headers.get('Content-Encoding', '').lower()
                if resp_enc == 'gzip':
                    try:
                        resp_data = gzip.decompress(resp_data)
                    except Exception:
                        pass
                globals_dict["current_coarena_idx"] = idx
                if _clear_attempt_cooldown:
                    _clear_attempt_cooldown("coarena", key, coarena_model, p_info=p_info, key_index=idx)
                else:
                    clear_key_cooldown("coarena", key, coarena_model)
                p_name = p_info.get("name", "Coarena")
                _record_winner_usage(handler, "coarena", p_name, coarena_model, f"Key #{idx+1}", resp_data, req_t0, key=key)
                resp_data = append_signature_to_response(resp_data, p_name, coarena_model)
                handler.send_response(resp_status)
                for k, val in resp_hdrs.items():
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
                if _mark_attempt_cooldown:
                    _mark_attempt_cooldown("coarena", key, e.code, coarena_model, err_body, headers=e.headers, p_info=p_info, key_index=idx)
                else:
                    mark_key_cooldown("coarena", key, e.code, coarena_model, err_body)
                record_live_issue("coarena", p_info.get("name", "Coarena"), coarena_model, f"Key #{idx+1}", e.code, err_body[:200])
                sys.stderr.write(f"[Proxy] Coarena key #{idx+1} HTTP error {e.code}: {err_body[:300]}. URL: {upstream_url}. Model: {coarena_model}.\n")
                if e.code in (400, 413):
                    err_low = err_body.lower()
                    is_model_err = ("model" in err_low) and ("not found" in err_low or "unknown model" in err_low or "invalid model" in err_low)
                    if is_model_err:
                        break
                    return False
                continue
            except Exception as e:
                record_live_issue("coarena", p_info.get("name", "Coarena"), coarena_model, f"Key #{idx+1}", 0, str(e))
                sys.stderr.write(f"[Proxy] Coarena key #{idx+1} network error: {e}. Trying next...\n")
                continue
    return False

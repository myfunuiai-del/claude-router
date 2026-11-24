#!/usr/bin/env python3
# Modularized per gemini.md Rule 2 (Limit 400-500 lines)
import json
import os
import sys
import time
import socket
import urllib.request
import urllib.error
import re
import random
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
_transform_mod = _load_module_to_globals("proxy_v2.transform-1.py", globals())
_multi_agent_mod = _load_module_to_globals("proxy_v2.multi_agent-1.py", globals())
_forwarder_loop_mod = _load_module_to_globals("proxy_v2.forwarder_loop-1.py", globals())
_balancer_mod = _load_module_to_globals("proxy_v2.key_balancer-1.py", globals())

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

def try_forward_with_history_recovery(handler, p_id, raw_body, body_obj, orig_model, allow_model_fallback=True):
    """Try forwarding original request to p_id with optional model fallback control.
    On 400/403/413 with trimmable history, escalate safely on the same provider.
    """
    handler._live_stage = "Original"
    if try_forward_provider(handler, p_id, raw_body, body_obj, orig_model, is_recovery=False, allow_model_fallback=allow_model_fallback):
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
            if try_forward_provider(handler, p_id, v_raw, v_body_obj, orig_model, is_recovery=True, allow_model_fallback=allow_model_fallback):
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
        # Check Redirection (Switch Account Only — 0 Quota) or normal Account-Model Binding
        try:
            from account_model_lock import check_and_enforce_binding, handle_redirection_switch_only
            redir_matched, acc_name, acc_email, switch_msg = handle_redirection_switch_only(orig_model)
            if redir_matched:
                confirm_text = f"✅ Account switched to **{acc_name}** (`{acc_email}`).\nRequest halted — **0 quota used**."
                is_stream = bool(body_obj.get("stream"))
                path_low = (getattr(handler, "path", "") or "").lower()
                is_openai = ("/chat/completions" in path_low)

                if is_stream:
                    handler.send_response(200)
                    handler.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                    handler.send_header('Cache-Control', 'no-cache')
                    handler.end_headers()
                    if is_openai:
                        chunk = {
                            "id": f"chatcmpl-switch-{int(time.time())}",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": orig_model,
                            "choices": [{"index": 0, "delta": {"role": "assistant", "content": confirm_text}, "finish_reason": "stop"}]
                        }
                        handler.wfile.write(f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode('utf-8'))
                    else:
                        msg_id = f"msg_switch_{int(time.time())}"
                        events = [
                            ("message_start", {"type": "message_start", "message": {"id": msg_id, "type": "message", "role": "assistant", "content": [], "model": orig_model, "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 0, "output_tokens": 0}}}),
                            ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": confirm_text}}),
                            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 0}}),
                            ("message_stop", {"type": "message_stop"})
                        ]
                        sse_body = "".join(f"event: {ev}\ndata: {json.dumps(pl)}\n\n" for ev, pl in events)
                        handler.wfile.write(sse_body.encode('utf-8'))
                    handler.wfile.flush()
                else:
                    if is_openai:
                        resp_obj = {
                            "id": f"chatcmpl-switch-{int(time.time())}",
                            "object": "chat.completion",
                            "created": int(time.time()),
                            "model": orig_model,
                            "choices": [{"index": 0, "message": {"role": "assistant", "content": confirm_text}, "finish_reason": "stop"}],
                            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                        }
                    else:
                        resp_obj = {
                            "id": f"msg_switch_{int(time.time())}",
                            "type": "message",
                            "role": "assistant",
                            "model": orig_model,
                            "content": [{"type": "text", "text": confirm_text}],
                            "stop_reason": "end_turn",
                            "stop_sequence": None,
                            "usage": {"input_tokens": 0, "output_tokens": 0}
                        }
                    payload = json.dumps(resp_obj).encode('utf-8')
                    handler.send_response(200)
                    handler.send_header('Content-Type', 'application/json')
                    handler.send_header('Content-Length', str(len(payload)))
                    handler.end_headers()
                    handler.wfile.write(payload)
                return
            check_and_enforce_binding(orig_model)
        except Exception:
            pass
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
        # 0. MULTI-AGENT TEAM INTERCEPTION: If requested model is a Multi-Agent Team (team:...) or path is /multiagent
        is_multiagent_path = handler.path == "/multiagent" or handler.path.startswith("/multiagent/") or handler.path.startswith("/multiagent?")
        target_team = None
        if orig_model and (orig_model.startswith("team:") or orig_model.startswith("multiagent/")):
            target_team = get_multi_agent_team(orig_model, cfg)
        elif is_multiagent_path:
            # If routed to /multiagent, use specified team model or first enabled team
            target_team = get_multi_agent_team(orig_model, cfg)
            if not target_team:
                teams = cfg.get("multi_agent_teams", {})
                for t in teams.values():
                    if t.get("enabled", True) is not False:
                        target_team = t
                        break

        if target_team:
            sys.stderr.write(f"[Proxy Multi-Agent] Intercepted team request for '{target_team.get('name')}' (Model: {orig_model}, Path: {handler.path})\n")
            execute_multi_agent_team(handler, target_team, body_obj, raw_body)
            return

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
            rl_cfg = p_info.get("rate_limit")
            if "is_provider_rate_limited" in globals():
                is_throttled, refill_s, reason = is_provider_rate_limited(target_dedicated_provider, rl_cfg)
                if is_throttled:
                    sys.stderr.write(f"[Proxy Direct Route] Dedicated server '{p_name}' quota exhausted ({reason}). Refills in {refill_s}s.\n")
                    handler.send_response(429)
                    handler.send_header('Content-Type', 'application/json')
                    handler.send_header('Retry-After', str(refill_s))
                    msg = json.dumps({"error": {"type": "rate_limit_exceeded", "message": f"Server '{p_name}' ({target_dedicated_provider}) has exhausted its configured quota ({reason}). Refills in {refill_s}s."}}).encode()
                    handler.send_header('Content-Length', str(len(msg)))
                    handler.end_headers()
                    handler.wfile.write(msg)
                    return
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

        # Helper: test if provider supports model parity
        def _prov_supports_model(p_id, p_info, model):
            if not model or model == "unknown":
                return False
            if p_id == "coarena":
                coa_sup = ("gemini-4-carbon", "gemini-3-8-flash", "deepseek-v4-1-flash-1017")
                c_tail = model.split("/")[-1]
                return model in coa_sup or c_tail in coa_sup
            p_models = p_info.get("models", [])
            c_tail = model.split("/")[-1].split(":")[0].lower()
            if model in p_models or any(c_tail == m.split("/")[-1].split(":")[0].lower() for m in p_models):
                return True
            p_def = p_info.get("default_model", "")
            return bool(p_def and (model == p_def or c_tail == p_def.split("/")[-1].split(":")[0].lower()))

        # PASS 1: MODEL PARITY FIRST (Exact/equivalent model search across all active routed servers)
        # Only providers with direct model parity match are attempted; quality degradation is prevented
        parity_order = [p for p in routed_providers if p in all_providers and _prov_supports_model(p, all_providers[p], orig_model)]

        success = False
        for prio_idx, p_id in enumerate(parity_order):
            p_info = all_providers.get(p_id, {})
            if p_info.get("enabled", True) is False:
                continue
            if "is_provider_rate_limited" in globals():
                is_throttled, refill_s, reason = is_provider_rate_limited(p_id, p_info.get("rate_limit"))
                if is_throttled:
                    p_name = p_info.get("name", p_id)
                    sys.stderr.write(f"[Proxy Pass 1 RateLimit] '{p_name}' quota exhausted ({reason}). Refills in {refill_s}s. Auto-skipping...\n")
                    failed_providers.append(f"{p_name} (Quota full, refill in {refill_s}s)")
                    continue

            sys.stderr.write(f"[Proxy Pass 1: Parity] Trying '{p_id}' for model '{orig_model}'...\n")
            if try_forward_with_history_recovery(handler, p_id, raw_body, body_obj, orig_model, allow_model_fallback=False):
                success = True
                _finish_success()
                return
            failed_providers.append(p_info.get("name", p_id))

        # PASS 2: QUALITY DEGRADATION / ALTERNATIVE MODEL FALLBACK
        # Only executed if Pass 1 failed across ALL active routed servers for the requested model
        if not success:
            sys.stderr.write(f"[Proxy Pass 2: Fallback] Model '{orig_model}' parity failed across all servers. Trying fallback models in pipeline order...\n")
            for prio_idx, p_id in enumerate(routed_providers):
                p_info = all_providers.get(p_id, {})
                if p_info.get("enabled", True) is False:
                    continue
                if "is_provider_rate_limited" in globals():
                    is_throttled, refill_s, reason = is_provider_rate_limited(p_id, p_info.get("rate_limit"))
                    if is_throttled:
                        continue

                sys.stderr.write(f"[Proxy Pass 2] Trying secondary/fallback models on '{p_id}'...\n")
                if try_forward_with_history_recovery(handler, p_id, raw_body, body_obj, orig_model, allow_model_fallback=True):
                    success = True
                    _finish_success()
                    return
                failed_providers.append(f"{p_info.get('name', p_id)} (Fallback)")

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

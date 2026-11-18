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
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
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
_balancer_mod = _load_module_to_globals("proxy_v2.key_balancer-1.py", globals())
def get_multi_agent_team(team_id_or_model, cfg=None):
    """Resolve a multi_agent_team from either 'team:<id>', '<id>', or model name."""
    if not team_id_or_model:
        return None
    if cfg is None:
        cfg = load_proxy_config()
    teams = cfg.get("multi_agent_teams", {})
    clean_id = team_id_or_model
    if clean_id.startswith("team:"):
        clean_id = clean_id[5:]
    if clean_id in teams:
        return teams[clean_id]
    for tid, t in teams.items():
        if tid == clean_id or t.get("slug") == clean_id or t.get("name") == clean_id:
            return t
    return None

def preflight_check_team(team, all_providers):
    """
    Strict All-or-Nothing Pre-Flight Check.
    Returns (True, None) if all member providers are healthy and ON.
    Returns (False, error_reason) if any member is disabled, missing keys, or cooling down.
    """
    members = team.get("members", [])
    if not members:
        return False, f"Team '{team.get('name')}' has no members configured."

    for idx, m in enumerate(members):
        pid = m.get("provider", "")
        p_obj = all_providers.get(pid)
        p_name = p_obj.get("name", pid) if p_obj else pid
        target_model = m.get("model", "")
        role = m.get("role", f"member_{idx+1}")

        if not p_obj:
            return False, f"Team Member #{idx+1} ({role}: {p_name}) does not exist in configured providers."

        if p_obj.get("enabled", True) is False:
            return False, f"Team Member #{idx+1} ({role}: {p_name}) is currently switched OFF. Multi-Agent teams require all members to be active."

        keys = p_obj.get("keys", [])
        if not keys and pid != "agentrouter":
            return False, f"Team Member #{idx+1} ({role}: {p_name}) has NO API keys provisioned."

        # Check if all keys of this member are on cooldown
        ready_keys = [k for k in keys if is_key_in_cooldown(pid, k, target_model) == 0]
        if keys and not ready_keys:
            return False, f"Team Member #{idx+1} ({role}: {p_name}) has all its API keys temporarily cooling down."

    return True, None

MANDATORY_CONCISE_RULE = "Be concise, output a structured blueprint only without filler text."

def _trim_handoff_text(text, max_chars=8000):
    """Smart Input Trimmer: Trims giant intermediate agent responses to prevent context/TPM explosion."""
    if not text or len(text) <= max_chars:
        return text
    half = (max_chars - 200) // 2
    return f"{text[:half]}\n\n[... Truncated for token limit ({len(text)} chars) ...]\n\n{text[-half:]}"

def _execute_member_turn(handler, pid, p_obj, target_model, body_obj, role_prompt=None, max_tokens=None, is_intermediate=False, is_first_member=False, member_mode=None):
    """
    Executes a single step with a specific member provider.
    Returns (True, response_bytes, in_tok, out_tok, elapsed_ms) or (False, error_msg, in_tok, out_tok, elapsed_ms).
    """
    p_name = p_obj.get("name", pid)
    p_type = p_obj.get("type", "anthropic")
    p_base = p_obj.get("base_url", "").rstrip("/")
    p_keys = p_obj.get("keys", [])
    t0 = time.time()

    b_copy = copy.deepcopy(body_obj) if body_obj else {"messages": []}
    b_copy["model"] = target_model

    # 1. Enforce Member 1 Invariant: even if user customizes prompt, concise rule is strictly preserved
    eff_prompt = (role_prompt or "").strip()
    if is_first_member:
        if not eff_prompt:
            eff_prompt = MANDATORY_CONCISE_RULE
        elif MANDATORY_CONCISE_RULE.lower() not in eff_prompt.lower():
            eff_prompt = f"{eff_prompt}\n\n[MANDATORY CONSTRAINT]: {MANDATORY_CONCISE_RULE}"

    # 2. Token Limit Management: User specified > Unlimited by default (no artificial capping)
    tok_val = int(max_tokens) if (max_tokens and str(max_tokens).isdigit() and int(max_tokens) > 0) else None
    if tok_val:
        b_copy["max_tokens"] = tok_val
    # If not specified, leave unlimited (retain client request tokens or full model limit)

    # 3. Smart Input Trimmer Guard: If conversation has many turns, prune older turns for intermediate stages
    messages = b_copy.get("messages", [])
    if is_intermediate and len(messages) > 6:
        # Keep initial task instruction + recent 4 turns (saves thousands of input tokens for intermediate agents)
        b_copy["messages"] = [messages[0]] + messages[-4:]

    # 4. System prompt assembly
    if eff_prompt:
        cur_sys = b_copy.get("system")
        if isinstance(cur_sys, str):
            b_copy["system"] = f"{eff_prompt}\n\n{cur_sys}" if cur_sys.strip() else eff_prompt
        elif isinstance(cur_sys, list):
            b_copy["system"] = [{"type": "text", "text": eff_prompt}] + list(cur_sys)
        else:
            b_copy["system"] = eff_prompt

    # 5. Resolve Engine Mode (agentic vs normal) & Adaptive Sequence
    init_mode = (member_mode or p_obj.get("mode") or ("normal" if is_first_member else "agentic")).lower()
    modes_sequence = [init_mode]
    if init_mode == "agentic":
        modes_sequence.append("normal")  # Adaptive fallback mode

    available_keys = [k for k in p_keys if is_key_in_cooldown(pid, k, target_model) == 0] or p_keys
    if not available_keys and pid != "agentrouter":
        return False, f"[{p_name}] No available keys", 0, 0, 0

    key = select_balanced_key(pid, available_keys, target_model, is_key_in_cooldown) if "select_balanced_key" in globals() else (available_keys[0] if available_keys else "auto")

    last_err_msg = ""
    for mode_idx, cur_mode in enumerate(modes_sequence):
        if mode_idx > 0:
            sys.stderr.write(f"[Multi-Agent Adaptive] Member '{pid}' ({target_model}) auto-downgraded from Agentic to Normal mode to bypass 429/400 bottleneck.\n")

        if p_type == "anthropic":
            fwd_url = f"{p_base}/v1/messages" if p_base.endswith("/api") else f"{p_base}/messages"
            eff_anth_body = apply_engine_mode_to_anthropic_body(b_copy, mode=cur_mode)
            payload = json.dumps(eff_anth_body).encode('utf-8')
            hdrs = {
                'Authorization': f"Bearer {key}",
                'x-api-key': key,
                'anthropic-version': '2023-06-01',
                'Originator': 'codex_cli_rs',
                'Content-Type': 'application/json',
                'Accept-Encoding': 'identity'
            }
            if p_obj.get("custom_headers") and isinstance(p_obj["custom_headers"], dict):
                hdrs.update(p_obj["custom_headers"])

            req = urllib.request.Request(fwd_url, data=payload, headers=hdrs, method='POST')
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = resp.read()
                    clear_key_cooldown(pid, key, target_model)
                    in_t, out_t = extract_anthropic_usage(data)
                    ms = int((time.time() - t0) * 1000)
                    return True, data, in_t, out_t, ms
            except urllib.error.HTTPError as e:
                err_body = ""
                try: err_body = e.read().decode('utf-8', errors='ignore')[:300]
                except Exception: pass
                mark_key_cooldown(pid, key, e.code, target_model, err_body)
                ms = int((time.time() - t0) * 1000)
                last_err_msg = f"HTTP {e.code} from {p_name}: {err_body}"
                if cur_mode == "agentic" and e.code in (400, 413, 429) and "normal" in modes_sequence[mode_idx+1:]:
                    continue
                return False, last_err_msg, 0, 0, ms
            except Exception as e:
                ms = int((time.time() - t0) * 1000)
                return False, f"Network error from {p_name}: {str(e)}", 0, 0, ms

        elif p_type == "openai":
            fwd_url = p_base if p_base.endswith("/chat/completions") else f"{p_base}/chat/completions"
            openai_body = anthropic_to_openai_body(b_copy, target_model, p_id=pid, mode=cur_mode, base_url=p_base)
            payload = json.dumps(openai_body, ensure_ascii=False).encode('utf-8')
            hdrs = {
                'Authorization': f"Bearer {key}",
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (compatible; Claude-Router-MultiAgent/1.0)',
                'Accept-Encoding': 'identity'
            }
            if p_obj.get("custom_headers") and isinstance(p_obj["custom_headers"], dict):
                hdrs.update(p_obj["custom_headers"])

            req = urllib.request.Request(fwd_url, data=payload, headers=hdrs, method='POST')
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    resp_data = resp.read()
                    clear_key_cooldown(pid, key, target_model)
                    text = resp_data.decode('utf-8', errors='ignore')
                    anth_resp = None
                    if b_copy.get("stream", False) or "data:" in text:
                        anth_resp = convert_openai_stream_to_anthropic(text, p_name, target_model)
                    else:
                        try:
                            o_json = json.loads(text)
                            anth_resp = convert_openai_json_to_anthropic(o_json, p_name, target_model)
                        except Exception:
                            anth_resp = resp_data
                    in_t, out_t = extract_anthropic_usage(anth_resp)
                    ms = int((time.time() - t0) * 1000)
                    return True, anth_resp, in_t, out_t, ms
            except urllib.error.HTTPError as e:
                err_body = ""
                try: err_body = e.read().decode('utf-8', errors='ignore')[:300]
                except Exception: pass
                mark_key_cooldown(pid, key, e.code, target_model, err_body)
                ms = int((time.time() - t0) * 1000)
                last_err_msg = f"HTTP {e.code} from {p_name}: {err_body}"
                if cur_mode == "agentic" and e.code in (400, 413, 429) and "normal" in modes_sequence[mode_idx+1:]:
                    continue
                return False, last_err_msg, 0, 0, ms
            except Exception as e:
                ms = int((time.time() - t0) * 1000)
                return False, f"Network error from {p_name}: {str(e)}", 0, 0, ms

    return False, last_err_msg or f"Unsupported provider type '{p_type}' for {p_name}", 0, 0, 0

def _extract_text_content(resp_data):
    """Reliably extracts plain text response from Anthropic or OpenAI payloads."""
    try:
        data_str = resp_data.decode('utf-8', errors='ignore')
        # Check if streaming SSE
        if "data: " in data_str:
            lines = data_str.split("\n")
            text = ""
            for line in lines:
                if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                    try:
                        chunk = json.loads(line[6:].strip())
                        delta = chunk.get("delta", {})
                        if isinstance(delta, dict) and delta.get("text"):
                            text += delta["text"]
                        choices = chunk.get("choices", [])
                        if choices and choices[0].get("delta", {}).get("content"):
                            text += choices[0]["delta"]["content"]
                    except Exception:
                        pass
            if text.strip():
                return text.strip()

        # Regular JSON
        s_obj = json.loads(data_str)
        if "content" in s_obj and isinstance(s_obj["content"], list):
            text = "".join(blk.get("text", "") for blk in s_obj["content"] if isinstance(blk, dict) and blk.get("type") == "text")
            if text.strip():
                return text.strip()
        if "choices" in s_obj and isinstance(s_obj["choices"], list) and len(s_obj["choices"]) > 0:
            msg = s_obj["choices"][0].get("message", {})
            if msg.get("content"):
                return msg["content"].strip()
        return data_str[:2500].strip()
    except Exception:
        return resp_data.decode('utf-8', errors='ignore')[:2500].strip()


def _send_team_error(handler, tname, failing_pid, err_msg, t_start):
    sys.stderr.write(f"[Multi-Agent Strict Halt] Team '{tname}' aborted due to member '{failing_pid}': {err_msg}\n")
    record_live_issue("multiagent", f"Team: {tname}", failing_pid, "Member Error", 502, err_msg[:200])
    record_live_request(
        "multiagent", f"🤖 Team: {tname}", failing_pid, "Member Failure",
        status="err", code=502, latency_ms=int((time.time() - t_start) * 1000),
        path=handler.path, recovery_stage="", failover_from=[f"Halted on member {failing_pid}"]
    )
    handler.send_response(502)
    handler.send_header('Content-Type', 'application/json')
    err_body = json.dumps({
        "error": {
            "type": "multi_agent_member_error",
            "message": f"Multi-Agent Team '{tname}' halted because member '{failing_pid}' failed: {err_msg}. Strict all-or-nothing policy enforced (did not leak to standby or failover pipeline)."
        }
    }).encode('utf-8')
    handler.send_header('Content-Length', str(len(err_body)))
    handler.end_headers()
    handler.wfile.write(err_body)

def _finish_team_success(handler, team, winner_pname, winner_model, resp_data, t_start, in_t, out_t, steps_log):
    tname = team.get("name", "Team")
    tid = team.get("id") or team.get("slug") or "team"
    elapsed_ms = max(1, int((time.time() - t_start) * 1000))
    tps = round(out_t / (elapsed_ms / 1000.0), 1) if (out_t > 0 and elapsed_ms > 50) else 0.0

    steps_summary = " ➔ ".join(steps_log)
    save_active_state(f"🤖 {tname}", f"{winner_pname} ({winner_model})", steps_summary, input_tokens=in_t, output_tokens=out_t, tok_per_sec=tps, latency_ms=elapsed_ms)

    record_live_request(
        "multiagent", f"🤖 Team: {tname}", f"{winner_pname}:{winner_model}", "Team Orchestra",
        status="ok", code=200, latency_ms=elapsed_ms,
        path=handler.path, recovery_stage=f"Multi-Agent Pipeline ({steps_summary})",
        failover_from=[], input_tokens=in_t, output_tokens=out_t, tok_per_sec=tps
    )

    handler.send_response(200)
    # Check if stream or json
    text = resp_data.decode('utf-8', errors='ignore')
    if "event: " in text or "data: " in text:
        handler.send_header('Content-Type', 'text/event-stream; charset=utf-8')
    else:
        handler.send_header('Content-Type', 'application/json')
    handler.send_header('Content-Length', str(len(resp_data)))
    handler.end_headers()
    handler.wfile.write(resp_data)

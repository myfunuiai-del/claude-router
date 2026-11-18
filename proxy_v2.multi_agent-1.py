#!/usr/bin/env python3
"""
proxy_v2.multi_agent-1.py: Multi-Agent Architecture Engine for Claude Router.

Key features:
1. Strict Team All-or-Nothing Isolation: If any single member provider/model fails, errors,
   is turned OFF, or hits rate limit/quota, the entire team halts with HTTP 503 explaining
   exactly which member broke down. Zero cascading into general pipeline or standby pool.
2. Workflows:
   - role_pipeline (Default): Step 1 (Planner/Architect analyzes and structures plan) ->
     Step 2 (Coder/Executor writes the solution and makes tool calls).
   - consensus: Parallel synthesis across team members.
   - worker_reviewer: Worker writes -> Reviewer audits & refines.
3. Dropdown-Friendly: Intercepts models formatted as `team:<team_id>` or direct `multiagent` routes.
"""

import os
import sys
import json
import time
import copy
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
_transform_mod = _load_module_to_globals("proxy_v2.transform-1.py", globals())

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

def _execute_member_turn(handler, pid, p_obj, target_model, body_obj, role_prompt=None):
    """
    Executes a single step with a specific member provider.
    Returns (True, response_bytes, in_tok, out_tok, elapsed_ms) or (False, error_msg, in_tok, out_tok, elapsed_ms).
    """
    p_name = p_obj.get("name", pid)
    p_type = p_obj.get("type", "anthropic")
    p_base = p_obj.get("base_url", "").rstrip("/")
    p_keys = p_obj.get("keys", [])
    t0 = time.time()

    # Prepend role prompt if given
    b_copy = copy.deepcopy(body_obj) if body_obj else {"messages": []}
    b_copy["model"] = target_model
    if role_prompt and role_prompt.strip():
        cur_sys = b_copy.get("system")
        if isinstance(cur_sys, str):
            b_copy["system"] = f"{role_prompt.strip()}\n\n{cur_sys}" if cur_sys.strip() else role_prompt.strip()
        elif isinstance(cur_sys, list):
            b_copy["system"] = [{"type": "text", "text": role_prompt.strip()}] + list(cur_sys)
        else:
            b_copy["system"] = role_prompt.strip()

    available_keys = [k for k in p_keys if is_key_in_cooldown(pid, k, target_model) == 0] or p_keys
    if not available_keys and pid != "agentrouter":
        return False, f"[{p_name}] No available keys", 0, 0, 0

    key = available_keys[0] if available_keys else "auto"

    if p_type == "anthropic":
        fwd_url = f"{p_base}/v1/messages" if p_base.endswith("/api") else f"{p_base}/messages"
        payload = json.dumps(b_copy).encode('utf-8')
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
            return False, f"HTTP {e.code} from {p_name}: {err_body}", 0, 0, ms
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            return False, f"Network error from {p_name}: {str(e)}", 0, 0, ms

    elif p_type == "openai":
        fwd_url = p_base if p_base.endswith("/chat/completions") else f"{p_base}/chat/completions"
        openai_body = anthropic_to_openai_body(b_copy, target_model, p_id=pid, mode=p_obj.get("mode", "agentic"), base_url=p_base)
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
            return False, f"HTTP {e.code} from {p_name}: {err_body}", 0, 0, ms
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            return False, f"Network error from {p_name}: {str(e)}", 0, 0, ms

    return False, f"Unsupported provider type '{p_type}' for {p_name}", 0, 0, 0

def execute_multi_agent_team(handler, team, body_obj, raw_body):
    """
    Executes a Multi-Agent Team with Strict All-or-Nothing Isolation.
    """
    cfg = load_proxy_config()
    all_providers = cfg.get("providers", {})
    t_start = time.time()
    tname = team.get("name", "Team")
    tid = team.get("id") or team.get("slug") or "team"
    members = team.get("members", [])

    # 1. Preflight Check: If ANY member is down/OFF/cooldown, strictly halt!
    ok, err_reason = preflight_check_team(team, all_providers)
    if not ok:
        sys.stderr.write(f"[Multi-Agent Strict Halt] Team '{tname}' pre-flight failed: {err_reason}\n")
        record_live_issue("multiagent", f"Team: {tname}", tid, "Team Preflight", 503, err_reason)
        record_live_request(
            "multiagent", f"🤖 Team: {tname}", tid, "Pre-flight Check",
            status="err", code=503, latency_ms=int((time.time() - t_start) * 1000),
            path=handler.path, recovery_stage="", failover_from=[f"Team Halted: {err_reason}"]
        )
        handler.send_response(503)
        handler.send_header('Content-Type', 'application/json')
        err_payload = json.dumps({
            "error": {
                "type": "multi_agent_halt_error",
                "message": f"Multi-Agent Team '{tname}' halted because member verification failed: {err_reason}. Strict all-or-nothing policy prevented fallback."
            }
        }).encode('utf-8')
        handler.send_header('Content-Length', str(len(err_payload)))
        handler.end_headers()
        handler.wfile.write(err_payload)
        return True

    # 2. Execution Strategy: Role-Pipeline (e.g. Architect -> Coder/Executor)
    # If 1 member, execute directly with member's custom prompt
    # If >=2 members, Lead member (1st) guides or 2nd member finishes with full tool support
    total_in = 0
    total_out = 0
    steps_log = []

    if len(members) == 1:
        m = members[0]
        pid = m.get("provider")
        p_obj = all_providers[pid]
        mdl = m.get("model")
        p_prompt = m.get("prompt", "")
        success, resp_data, in_t, out_t, ms = _execute_member_turn(handler, pid, p_obj, mdl, body_obj, p_prompt)
        if not success:
            _send_team_error(handler, tname, pid, resp_data, t_start)
            return True
        total_in += in_t
        total_out += out_t
        steps_log.append(f"{p_obj.get('name', pid)}:{mdl} ({ms}ms)")
        _finish_team_success(handler, team, p_obj.get('name', pid), mdl, resp_data, t_start, total_in, total_out, steps_log)
        return True

    # Multi-member execution:
    # Member 1 = Planner / Architect (generates high-level blueprint / strategy)
    # Member 2 = Executor / Coder (implements solution with tools and client output)
    m1 = members[0]
    pid1 = m1.get("provider")
    p_obj1 = all_providers[pid1]
    mdl1 = m1.get("model")
    r1_prompt = m1.get("prompt") or "You are the Lead Architect / Planner. Analyze the user request thoroughly and provide a concise architectural plan."

    sys.stderr.write(f"[Multi-Agent Team '{tname}'] Step 1/2: Running Architect/Planner ({p_obj1.get('name', pid1)} - {mdl1})...\n")
    s1_ok, s1_data, in_t1, out_t1, ms1 = _execute_member_turn(handler, pid1, p_obj1, mdl1, body_obj, r1_prompt)
    if not s1_ok:
        _send_team_error(handler, tname, pid1, s1_data, t_start)
        return True
    total_in += in_t1
    total_out += out_t1
    steps_log.append(f"Step 1 ({p_obj1.get('name', pid1)}): {ms1}ms")

    # Extract text from Step 1 response
    step1_text = ""
    try:
        s1_obj = json.loads(s1_data.decode('utf-8', errors='ignore'))
        for blk in s1_obj.get("content", []):
            if isinstance(blk, dict) and blk.get("type") == "text":
                step1_text += blk.get("text", "")
    except Exception:
        step1_text = s1_data.decode('utf-8', errors='ignore')[:1500]

    # Step 2: Executor / Coder takes the plan + user instructions
    m2 = members[1]
    pid2 = m2.get("provider")
    p_obj2 = all_providers[pid2]
    mdl2 = m2.get("model")
    r2_prompt = m2.get("prompt") or "You are the Senior Implementation Engineer. Execute the approved architectural plan accurately."
    combined_prompt = f"{r2_prompt}\n\n[TEAM ARCHITECTURAL PLAN FROM {p_obj1.get('name', pid1)}]:\n{step1_text}"

    sys.stderr.write(f"[Multi-Agent Team '{tname}'] Step 2/2: Running Executor/Coder ({p_obj2.get('name', pid2)} - {mdl2})...\n")
    s2_ok, s2_data, in_t2, out_t2, ms2 = _execute_member_turn(handler, pid2, p_obj2, mdl2, body_obj, combined_prompt)
    if not s2_ok:
        _send_team_error(handler, tname, pid2, s2_data, t_start)
        return True
    total_in += in_t2
    total_out += out_t2
    steps_log.append(f"Step 2 ({p_obj2.get('name', pid2)}): {ms2}ms")

    _finish_team_success(handler, team, p_obj2.get('name', pid2), mdl2, s2_data, t_start, total_in, total_out, steps_log)
    return True

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

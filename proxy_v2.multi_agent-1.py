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
_runner_mod = _load_module_to_globals("proxy_v2.multi_agent_runner-1.py", globals())

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

    # 2. Execution Strategy: Check workflow
    wf = team.get("workflow", "role_pipeline")
    total_in = 0
    total_out = 0
    steps_log = []
    steps_detail = []

    def _add_step_trace(role, p_name, mdl, m_mode, ms, in_t, out_t, data):
        txt = _extract_text_content(data) if data else ""
        steps_detail.append({
            "step": len(steps_detail) + 1,
            "role": role,
            "provider": p_name,
            "model": mdl,
            "mode": m_mode or "normal",
            "latency_ms": ms,
            "in_tokens": in_t,
            "out_tokens": out_t,
            "snippet": txt[:300]
        })

    if len(members) == 1:
        m = members[0]
        pid = m.get("provider")
        p_obj = all_providers[pid]
        mdl = m.get("model")
        p_prompt = m.get("prompt", "")
        success, resp_data, in_t, out_t, ms = _execute_member_turn(
            handler, pid, p_obj, mdl, body_obj, p_prompt,
            max_tokens=m.get("tokens"), member_mode=m.get("mode")
        )
        if not success:
            _send_team_error(handler, tname, pid, resp_data, t_start)
            return True
        total_in += in_t
        total_out += out_t
        steps_log.append(f"{p_obj.get('name', pid)}:{mdl} ({ms}ms)")
        _finish_team_success(handler, team, p_obj.get('name', pid), mdl, resp_data, t_start, total_in, total_out, steps_log, steps_detail=steps_detail)
        return True

    # ==========================================
    # STRATEGY 1: PARALLEL COUNCIL / JUDGE CONSENSUS
    # ==========================================
    if wf in ("parallel_council", "consensus", "judge_consensus"):
        councilors = members[:-1]
        judge = members[-1]

        j_pid = judge.get("provider")
        j_pobj = all_providers[j_pid]
        j_mdl = judge.get("model")

        sys.stderr.write(f"[Multi-Agent Parallel Council '{tname}'] Fanning out {len(councilors)} councilors in parallel...\n")

        council_results = [None] * len(councilors)
        council_errors = []

        def _run_councilor(idx, mem):
            c_pid = mem.get("provider")
            c_pobj = all_providers[c_pid]
            c_mdl = mem.get("model")
            c_role = mem.get("role") or f"Councilor #{idx+1}"
            c_prompt = mem.get("prompt") or f"You are {c_role}. Provide your complete, independent solution to the problem."
            c_tok = mem.get("tokens") or mem.get("max_tokens")
            c_mode = mem.get("mode") or "normal"
            ok, data, in_t, out_t, ms = _execute_member_turn(
                handler, c_pid, c_pobj, c_mdl, body_obj, c_prompt,
                max_tokens=c_tok, is_intermediate=True, is_first_member=(idx == 0),
                member_mode=c_mode
            )
            return idx, c_pid, c_pobj.get("name", c_pid), c_mdl, c_role, ok, data, in_t, out_t, ms

        t_fanout = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(councilors))) as executor:
            futures = [executor.submit(_run_councilor, i, m) for i, m in enumerate(councilors)]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    idx, c_pid, c_pname, c_mdl, c_role, ok, data, in_t, out_t, ms = fut.result()
                    if not ok:
                        council_errors.append((c_pid, data))
                    else:
                        council_results[idx] = {
                            "pid": c_pid, "pname": c_pname, "model": c_mdl,
                            "role": c_role, "data": data, "in_t": in_t, "out_t": out_t, "ms": ms
                        }
                except Exception as e:
                    council_errors.append(("worker_thread", str(e)))

        # Strict All-or-Nothing check: If ANY councilor failed, abort!
        if council_errors:
            failing_pid, err_msg = council_errors[0]
            _send_team_error(handler, tname, failing_pid, err_msg, t_start)
            return True

        parallel_ms = int((time.time() - t_fanout) * 1000)
        c_summaries = []
        council_opinions_text = ""

        for idx, cr in enumerate(council_results):
            total_in += cr["in_t"]
            total_out += cr["out_t"]
            c_summaries.append(f"{cr['pname']} ({cr['ms']}ms)")
            c_text = _trim_handoff_text(_extract_text_content(cr["data"]))
            council_opinions_text += f"\n--- [COUNCILOR CANDIDATE #{idx+1}: {cr['role']} ({cr['pname']} • {cr['model']})] ---\n{c_text.strip()}\n"

        steps_log.append(f"Parallel Council [{', '.join(c_summaries)} in {parallel_ms}ms]")

        # Phase 2: Supreme Judge / Synthesizer makes final verdict
        judge_default_prompt = (
            "You are the Supreme Judge and Master Synthesizer. "
            "You have received candidate solutions from independent expert councilors. "
            "Critically analyze all solutions, eliminate errors, reconcile any contradictions, "
            "and output the final, authoritative, bug-free, and most optimal solution for the user."
        )
        j_prompt = judge.get("prompt") or judge_default_prompt
        combined_judge_prompt = f"{j_prompt}\n\n{council_opinions_text}\n--- [END OF COUNCIL OPINIONS] ---"
        j_tok = judge.get("tokens") or judge.get("max_tokens")
        j_mode = judge.get("mode") or "agentic"

        sys.stderr.write(f"[Multi-Agent Parallel Council '{tname}'] Phase 2: Supreme Judge ({j_pobj.get('name', j_pid)} - {j_mdl}) evaluating...\n")
        j_ok, j_data, j_in, j_out, j_ms = _execute_member_turn(
            handler, j_pid, j_pobj, j_mdl, body_obj, combined_judge_prompt,
            max_tokens=j_tok, is_intermediate=False, is_first_member=False,
            member_mode=j_mode
        )
        if not j_ok:
            _send_team_error(handler, tname, j_pid, j_data, t_start)
            return True

        total_in += j_in
        total_out += j_out
        steps_log.append(f"Judge Verdict ({j_pobj.get('name', j_pid)}): {j_ms}ms")

        _finish_team_success(handler, team, j_pobj.get('name', j_pid), j_mdl, j_data, t_start, total_in, total_out, steps_log, steps_detail=steps_detail)
        return True

    # ==========================================
    # STRATEGY 2: FULL CYCLE TRI-TIER (Architect ➔ Builder ➔ Auditor)
    # ==========================================
    if wf == "plan_execute_audit" and len(members) >= 3:
        m1, m2, m3 = members[0], members[1], members[2]
        pid1, pid2, pid3 = m1.get("provider"), m2.get("provider"), m3.get("provider")
        pobj1, pobj2, pobj3 = all_providers[pid1], all_providers[pid2], all_providers[pid3]
        mdl1, mdl2, mdl3 = m1.get("model"), m2.get("model"), m3.get("model")

        r1_prompt = m1.get("prompt") or "System Architect: Analyze requirements, outline components, interfaces, and safety invariants. Be concise, output a structured blueprint only without filler text."
        sys.stderr.write(f"[Multi-Agent Tri-Tier '{tname}'] Tier 1: Architect ({pobj1.get('name', pid1)} - {mdl1})...\n")
        s1_ok, s1_data, in_t1, out_t1, ms1 = _execute_member_turn(
            handler, pid1, pobj1, mdl1, body_obj, r1_prompt,
            max_tokens=m1.get("tokens"), is_intermediate=True, is_first_member=True,
            member_mode=m1.get("mode") or "normal"
        )
        if not s1_ok:
            _send_team_error(handler, tname, pid1, s1_data, t_start)
            return True
        total_in += in_t1
        total_out += out_t1
        steps_log.append(f"Architect ({pobj1.get('name', pid1)}): {ms1}ms")
        plan_text = _trim_handoff_text(_extract_text_content(s1_data))

        r2_prompt = m2.get("prompt") or "Lead Builder: Implement complete, functional code following the architectural plan."
        builder_combined = f"{r2_prompt}\n\n[ARCHITECTURAL SPECIFICATION FROM {pobj1.get('name', pid1)}]:\n{plan_text}"
        sys.stderr.write(f"[Multi-Agent Tri-Tier '{tname}'] Tier 2: Builder ({pobj2.get('name', pid2)} - {mdl2})...\n")
        s2_ok, s2_data, in_t2, out_t2, ms2 = _execute_member_turn(
            handler, pid2, pobj2, mdl2, body_obj, builder_combined,
            max_tokens=m2.get("tokens"), is_intermediate=True, is_first_member=False,
            member_mode=m2.get("mode") or "agentic"
        )
        if not s2_ok:
            _send_team_error(handler, tname, pid2, s2_data, t_start)
            return True
        total_in += in_t2
        total_out += out_t2
        steps_log.append(f"Builder ({pobj2.get('name', pid2)}): {ms2}ms")
        code_text = _trim_handoff_text(_extract_text_content(s2_data))

        r3_prompt = m3.get("prompt") or "Security & Bug Auditor: Rigorously audit the built code for edge cases, security flaws, and performance regressions; output the final verified version."
        auditor_combined = (
            f"{r3_prompt}\n\n"
            f"[SYSTEM ARCHITECT SPECIFICATION]:\n{plan_text}\n\n"
            f"[BUILDER IMPLEMENTATION FROM {pobj2.get('name', pid2)}]:\n{code_text}\n\n"
            f"TASK: Conduct final audit against specifications, patch all edge-cases/bugs, and deliver the final verified solution to the user."
        )
        sys.stderr.write(f"[Multi-Agent Tri-Tier '{tname}'] Tier 3: Auditor ({pobj3.get('name', pid3)} - {mdl3})...\n")
        s3_ok, s3_data, in_t3, out_t3, ms3 = _execute_member_turn(
            handler, pid3, pobj3, mdl3, body_obj, auditor_combined,
            max_tokens=m3.get("tokens"), is_intermediate=False, is_first_member=False,
            member_mode=m3.get("mode") or "agentic"
        )
        if not s3_ok:
            _send_team_error(handler, tname, pid3, s3_data, t_start)
            return True
        total_in += in_t3
        total_out += out_t3
        steps_log.append(f"Auditor ({pobj3.get('name', pid3)}): {ms3}ms")

        _finish_team_success(handler, team, pobj3.get('name', pid3), mdl3, s3_data, t_start, total_in, total_out, steps_log, steps_detail=steps_detail)
        return True

    # ==========================================
    # STRATEGY 3: SPECULATIVE DRAFT (Fast Drafter ➔ Deep Finisher)
    # ==========================================
    if wf == "speculative_draft" and len(members) >= 2:
        m1, m2 = members[0], members[1]
        pid1, pid2 = m1.get("provider"), m2.get("provider")
        pobj1, pobj2 = all_providers[pid1], all_providers[pid2]
        mdl1, mdl2 = m1.get("model"), m2.get("model")

        r1_prompt = m1.get("prompt") or "Rapid Prototyper: Generate an immediate structural scaffold, pseudocode, and key draft without hesitation. Be concise, output a structured blueprint only without filler text."
        sys.stderr.write(f"[Multi-Agent Speculative Draft '{tname}'] Stage 1: Lightning Drafter ({pobj1.get('name', pid1)} - {mdl1})...\n")
        s1_ok, s1_data, in_t1, out_t1, ms1 = _execute_member_turn(
            handler, pid1, pobj1, mdl1, body_obj, r1_prompt,
            max_tokens=m1.get("tokens"), is_intermediate=True, is_first_member=True,
            member_mode=m1.get("mode") or "normal"
        )
        if not s1_ok:
            _send_team_error(handler, tname, pid1, s1_data, t_start)
            return True
        total_in += in_t1
        total_out += out_t1
        steps_log.append(f"Fast Draft ({pobj1.get('name', pid1)}): {ms1}ms")
        draft_text = _trim_handoff_text(_extract_text_content(s1_data))

        r2_prompt = m2.get("prompt") or "Deep Reasoning Finisher: Take the rapid draft, complete all implementations, enforce production hardening, and produce the final polished response."
        combined_prompt = (
            f"{r2_prompt}\n\n"
            f"[LIGHTNING DRAFT / SKELETON FROM {pobj1.get('name', pid1)}]:\n{draft_text}\n\n"
            f"TASK: Expand, harden, and produce the complete, production-ready solution."
        )
        sys.stderr.write(f"[Multi-Agent Speculative Draft '{tname}'] Stage 2: Deep Finisher ({pobj2.get('name', pid2)} - {mdl2})...\n")
        s2_ok, s2_data, in_t2, out_t2, ms2 = _execute_member_turn(
            handler, pid2, pobj2, mdl2, body_obj, combined_prompt,
            max_tokens=m2.get("tokens"), is_intermediate=False, is_first_member=False,
            member_mode=m2.get("mode") or "agentic"
        )
        if not s2_ok:
            _send_team_error(handler, tname, pid2, s2_data, t_start)
            return True
        total_in += in_t2
        total_out += out_t2
        steps_log.append(f"Deep Finish ({pobj2.get('name', pid2)}): {ms2}ms")

        _finish_team_success(handler, team, pobj2.get('name', pid2), mdl2, s2_data, t_start, total_in, total_out, steps_log, steps_detail=steps_detail)
        return True

    # ==========================================
    # STRATEGY 4: ROUTER EVALUATOR (Complexity Gatekeeper ➔ Expert)
    # ==========================================
    if wf == "router_evaluator" and len(members) >= 2:
        m1, m2 = members[0], members[1]
        pid1, pid2 = m1.get("provider"), m2.get("provider")
        pobj1, pobj2 = all_providers[pid1], all_providers[pid2]
        mdl1, mdl2 = m1.get("model"), m2.get("model")

        r1_prompt = m1.get("prompt") or "Complexity Gatekeeper: Classify user query complexity (1-10) and outline whether it requires simple immediate answer or full deep analysis. Be concise, output a structured blueprint only without filler text."
        sys.stderr.write(f"[Multi-Agent Router Evaluator '{tname}'] Stage 1: Gatekeeper ({pobj1.get('name', pid1)} - {mdl1})...\n")
        s1_ok, s1_data, in_t1, out_t1, ms1 = _execute_member_turn(
            handler, pid1, pobj1, mdl1, body_obj, r1_prompt,
            max_tokens=m1.get("tokens"), is_intermediate=True, is_first_member=True,
            member_mode=m1.get("mode") or "normal"
        )
        if not s1_ok:
            _send_team_error(handler, tname, pid1, s1_data, t_start)
            return True
        total_in += in_t1
        total_out += out_t1
        steps_log.append(f"Gatekeeper ({pobj1.get('name', pid1)}): {ms1}ms")
        eval_text = _trim_handoff_text(_extract_text_content(s1_data))

        r2_prompt = m2.get("prompt") or "Domain Specialist: Deliver the complete authoritative solution tailored to the evaluated complexity."
        combined_prompt = (
            f"{r2_prompt}\n\n"
            f"[QUERY COMPLEXITY EVALUATION FROM {pobj1.get('name', pid1)}]:\n{eval_text}\n\n"
            f"TASK: Provide the complete authoritative answer adhering to the evaluated scope and requirements."
        )
        sys.stderr.write(f"[Multi-Agent Router Evaluator '{tname}'] Stage 2: Expert Specialist ({pobj2.get('name', pid2)} - {mdl2})...\n")
        s2_ok, s2_data, in_t2, out_t2, ms2 = _execute_member_turn(
            handler, pid2, pobj2, mdl2, body_obj, combined_prompt,
            max_tokens=m2.get("tokens"), is_intermediate=False, is_first_member=False,
            member_mode=m2.get("mode") or "agentic"
        )
        if not s2_ok:
            _send_team_error(handler, tname, pid2, s2_data, t_start)
            return True
        total_in += in_t2
        total_out += out_t2
        steps_log.append(f"Expert ({pobj2.get('name', pid2)}): {ms2}ms")

        _finish_team_success(handler, team, pobj2.get('name', pid2), mdl2, s2_data, t_start, total_in, total_out, steps_log, steps_detail=steps_detail)
        return True

    # ==========================================
    # STRATEGY 5: WORKER ➔ REVIEWER (Draft ➔ Polish)
    # ==========================================
    if wf == "worker_reviewer" and len(members) >= 2:
        m1, m2 = members[0], members[1]
        pid1, pid2 = m1.get("provider"), m2.get("provider")
        pobj1, pobj2 = all_providers[pid1], all_providers[pid2]
        mdl1, mdl2 = m1.get("model"), m2.get("model")

        r1_prompt = m1.get("prompt") or "Primary Worker: Draft initial complete response addressing the user request. Be concise, output a structured blueprint only without filler text."
        sys.stderr.write(f"[Multi-Agent Worker-Reviewer '{tname}'] Stage 1: Worker ({pobj1.get('name', pid1)} - {mdl1})...\n")
        s1_ok, s1_data, in_t1, out_t1, ms1 = _execute_member_turn(
            handler, pid1, pobj1, mdl1, body_obj, r1_prompt,
            max_tokens=m1.get("tokens"), is_intermediate=True, is_first_member=True,
            member_mode=m1.get("mode") or "normal"
        )
        if not s1_ok:
            _send_team_error(handler, tname, pid1, s1_data, t_start)
            return True
        total_in += in_t1
        total_out += out_t1
        steps_log.append(f"Worker ({pobj1.get('name', pid1)}): {ms1}ms")
        draft_text = _trim_handoff_text(_extract_text_content(s1_data))

        r2_prompt = m2.get("prompt") or "Senior Reviewer: Polish wording, correct any technical inaccuracies, and present the final refined answer."
        combined_prompt = (
            f"{r2_prompt}\n\n"
            f"[INITIAL DRAFT FROM WORKER {pobj1.get('name', pid1)}]:\n{draft_text}\n\n"
            f"TASK: Thoroughly review, polish, fix any errors, and deliver the final refined response."
        )
        sys.stderr.write(f"[Multi-Agent Worker-Reviewer '{tname}'] Stage 2: Reviewer ({pobj2.get('name', pid2)} - {mdl2})...\n")
        s2_ok, s2_data, in_t2, out_t2, ms2 = _execute_member_turn(
            handler, pid2, pobj2, mdl2, body_obj, combined_prompt,
            max_tokens=m2.get("tokens"), is_intermediate=False, is_first_member=False,
            member_mode=m2.get("mode") or "agentic"
        )
        if not s2_ok:
            _send_team_error(handler, tname, pid2, s2_data, t_start)
            return True
        total_in += in_t2
        total_out += out_t2
        steps_log.append(f"Reviewer ({pobj2.get('name', pid2)}): {ms2}ms")

        _finish_team_success(handler, team, pobj2.get('name', pid2), mdl2, s2_data, t_start, total_in, total_out, steps_log, steps_detail=steps_detail)
        return True

    # ==========================================
    # STRATEGY 6: ROLE-PIPELINE (Architect ➔ Coder / Default Sequential)
    # ==========================================
    m1 = members[0]
    pid1 = m1.get("provider")
    p_obj1 = all_providers[pid1]
    mdl1 = m1.get("model")
    r1_prompt = m1.get("prompt") or "You are the Lead Architect / Planner. Analyze the user request thoroughly and provide a concise architectural plan. Be concise, output a structured blueprint only without filler text."

    sys.stderr.write(f"[Multi-Agent Team '{tname}'] Step 1/2: Running Architect/Planner ({p_obj1.get('name', pid1)} - {mdl1})...\n")
    s1_ok, s1_data, in_t1, out_t1, ms1 = _execute_member_turn(
        handler, pid1, p_obj1, mdl1, body_obj, r1_prompt,
        max_tokens=m1.get("tokens"), is_intermediate=True, is_first_member=True,
        member_mode=m1.get("mode") or "normal"
    )
    if not s1_ok:
        _send_team_error(handler, tname, pid1, s1_data, t_start)
        return True
    total_in += in_t1
    total_out += out_t1
    steps_log.append(f"Step 1 ({p_obj1.get('name', pid1)}): {ms1}ms")
    _add_step_trace(m1.get("role", "architect"), p_obj1.get('name', pid1), mdl1, m1.get("mode", "normal"), ms1, in_t1, out_t1, s1_data)
    step1_text = _trim_handoff_text(_extract_text_content(s1_data))

    m2 = members[1]
    pid2 = m2.get("provider")
    p_obj2 = all_providers[pid2]
    mdl2 = m2.get("model")
    r2_prompt = m2.get("prompt") or "You are the Senior Implementation Engineer. Execute the approved architectural plan accurately."
    combined_prompt = f"{r2_prompt}\n\n[TEAM ARCHITECTURAL PLAN FROM {p_obj1.get('name', pid1)}]:\n{step1_text}"

    sys.stderr.write(f"[Multi-Agent Team '{tname}'] Step 2/2: Running Executor/Coder ({p_obj2.get('name', pid2)} - {mdl2})...\n")
    s2_ok, s2_data, in_t2, out_t2, ms2 = _execute_member_turn(
        handler, pid2, p_obj2, mdl2, body_obj, combined_prompt,
        max_tokens=m2.get("tokens"), is_intermediate=False, is_first_member=False,
        member_mode=m2.get("mode") or "agentic"
    )
    if not s2_ok:
        _send_team_error(handler, tname, pid2, s2_data, t_start)
        return True
    total_in += in_t2
    total_out += out_t2
    steps_log.append(f"Step 2 ({p_obj2.get('name', pid2)}): {ms2}ms")
    _add_step_trace(m2.get("role", "coder"), p_obj2.get('name', pid2), mdl2, m2.get("mode", "agentic"), ms2, in_t2, out_t2, s2_data)

    _finish_team_success(handler, team, p_obj2.get('name', pid2), mdl2, s2_data, t_start, total_in, total_out, steps_log, steps_detail=steps_detail)
    return True


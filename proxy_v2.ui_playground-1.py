# proxy_v2.ui_playground-1.py - In-Dashboard Multi-Agent Dry Run Playground API
# Modularized per gemini.md Rule 2 (Limit 400-500 lines)

import json
import time
import os
import sys
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
_runner_mod = _load_module_to_globals("proxy_v2.multi_agent_runner-1.py", globals())

def handle_ui_playground_post(handler, raw_body):
    """Handle /api/ui/team-dry-run requests for dashboard playground."""
    if handler.path != "/api/ui/team-dry-run":
        return False

    try:
        data = json.loads(raw_body.decode('utf-8'))
        team_id = (data.get("team_id") or "").strip()
        user_prompt = (data.get("prompt") or "").strip()

        if not team_id or not user_prompt:
            handler.send_response(400)
            handler.send_header('Content-Type', 'application/json')
            err = json.dumps({"status": "error", "message": "team_id and prompt are required"}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

        cfg = load_proxy_config()
        team = cfg.get("multi_agent_teams", {}).get(team_id)
        all_providers = cfg.get("providers", {})

        if not team:
            handler.send_response(404)
            handler.send_header('Content-Type', 'application/json')
            err = json.dumps({"status": "error", "message": f"Team '{team_id}' not found"}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

        members = team.get("members", [])
        if not members:
            handler.send_response(400)
            handler.send_header('Content-Type', 'application/json')
            err = json.dumps({"status": "error", "message": "Team has no configured members"}).encode()
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

        t_start = time.time()
        body_obj = {"messages": [{"role": "user", "content": user_prompt}], "max_tokens": 4096}
        steps_out = []
        accumulated_text = ""
        total_in = 0
        total_out = 0

        for idx, m in enumerate(members):
            pid = m.get("provider")
            p_obj = all_providers.get(pid, {})
            model = m.get("model")
            role = m.get("role", f"Member {idx+1}")
            m_mode = m.get("mode") or ("normal" if idx == 0 else "agentic")
            r_prompt = m.get("prompt", "")

            # Combine prior step text if sequential
            step_prompt = r_prompt
            if accumulated_text:
                step_prompt = f"{r_prompt}\n\n[INPUT FROM PREVIOUS AGENT]:\n{accumulated_text}" if r_prompt else f"[INPUT FROM PREVIOUS AGENT]:\n{accumulated_text}"

            step_ok, resp_data, in_tok, out_tok, ms = _execute_member_turn(
                handler, pid, p_obj, model, body_obj, step_prompt,
                max_tokens=m.get("tokens"), is_intermediate=(idx < len(members)-1),
                is_first_member=(idx == 0), member_mode=m_mode
            )

            if not step_ok:
                handler.send_response(502)
                handler.send_header('Content-Type', 'application/json')
                err = json.dumps({
                    "status": "error",
                    "failed_step": idx + 1,
                    "failed_role": role,
                    "message": resp_data,
                    "completed_steps": steps_out
                }).encode()
                handler.send_header('Content-Length', str(len(err)))
                handler.end_headers()
                handler.wfile.write(err)
                return True

            total_in += in_tok
            total_out += out_tok
            step_text = _extract_text_content(resp_data)
            accumulated_text = step_text

            steps_out.append({
                "step": idx + 1,
                "role": role,
                "provider": p_obj.get("name", pid),
                "model": model,
                "mode": m_mode,
                "latency_ms": ms,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "output_text": step_text
            })

        total_elapsed = int((time.time() - t_start) * 1000)
        tps = round(total_out / (total_elapsed / 1000.0), 1) if (total_out > 0 and total_elapsed > 50) else 0.0

        resp = json.dumps({
            "status": "ok",
            "team_id": team_id,
            "team_name": team.get("name", team_id),
            "workflow": team.get("workflow", "role_pipeline"),
            "total_latency_ms": total_elapsed,
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "tok_per_sec": tps,
            "steps": steps_out,
            "final_output": accumulated_text
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
        err = json.dumps({"status": "error", "message": str(e)}).encode()
        handler.send_header('Content-Length', str(len(err)))
        handler.end_headers()
        handler.wfile.write(err)
        return True

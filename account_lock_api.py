#!/usr/bin/env python3
"""
Account-Model Binding UI & HTTP API Handler.
Dedicated handler for GET and POST endpoints related to Account Model Lock.
Uses exact authentic model catalog from AntiGem UI.
"""
import json
import os
import time
import account_model_lock

EXACT_MODELS = [
    "Gemini 3.8 Flash",
    "Gemini 4 Neon",
    "Gemini 4 Neon (XHigh)",
    "Gemini 4 Hydrogen",
    "Gemini 4 Hydrogen (XHigh)",
    "Orchestrator (Neon)",
    "Claude Sonnet 4.6",
    "Claude Opus 4.6",
    "GPT-OSS 120B",
    "Gemini 4 Argon",
    "Orchestrator (Argon)"
]

def handle_account_lock_get(handler):
    """Handles GET /api/ui/account-lock"""
    try:
        state = account_model_lock.load_state()
        resp_payload = {
            "status": "ok",
            "state": state,
            "current_email": account_model_lock.get_current_live_email(),
            "available_accounts": account_model_lock.list_available_accounts(),
            "models": EXACT_MODELS
        }
        resp = json.dumps(resp_payload).encode('utf-8')
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

def handle_account_lock_post(handler, raw_body):
    """Handles POST /api/ui/account-lock"""
    if handler.path != "/api/ui/account-lock":
        return False
    try:
        data = json.loads(raw_body.decode('utf-8'))
        state = account_model_lock.load_state()
        action = data.get("action", "toggle")

        if action == "force_switch":
            flag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".force_switch")
            with open(flag_path, "w") as f:
                f.write("force")
            resp = json.dumps({"status": "ok", "message": "Force switch signal sent"}).encode()
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True

        if action == "sync_models":
            resp_payload = {
                "status": "ok",
                "models": EXACT_MODELS
            }
            resp = json.dumps(resp_payload).encode('utf-8')
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.send_header('Content-Length', str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
            return True

        if action == "toggle":
            state["enabled"] = bool(data.get("enabled", not state.get("enabled", False)))
            account_model_lock.save_state(state)
        elif action == "save":
            if "accounts" in data:
                state["accounts"] = data["accounts"]
            if "enabled" in data:
                state["enabled"] = bool(data["enabled"])
            if "redirections" in data:
                state["redirections"] = data["redirections"]
            if "redirections_enabled" in data:
                state["redirections_enabled"] = bool(data["redirections_enabled"])
            if "custom_models" in data:
                state["custom_models"] = data["custom_models"]
            account_model_lock.save_state(state)
        elif action == "save_redirections":
            if "redirections" in data:
                state["redirections"] = data["redirections"]
            account_model_lock.save_state(state)
        elif action == "update_account":
            acc_id = data.get("id")
            for acc in state.get("accounts", []):
                if acc.get("id") == acc_id:
                    if "name" in data:
                        acc["name"] = data["name"]
                    if "models" in data:
                        acc["models"] = data["models"]
                    break
            account_model_lock.save_state(state)

        resp_payload = {
            "status": "ok",
            "state": state,
            "current_email": account_model_lock.get_current_live_email(),
            "available_accounts": account_model_lock.list_available_accounts(),
            "models": EXACT_MODELS
        }
        resp = json.dumps(resp_payload).encode('utf-8')
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

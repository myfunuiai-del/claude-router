#!/usr/bin/env python3
"""
Account-Model Binding & Auto Token Switcher for AntiGem / Claude-Router.
Enforces that requests to specific model families (e.g. Gemini 3.8 Flash, Neon, Neon XHigh)
run under the bound Google account. Supports Model Redirections / Aliasing.
Can be globally enabled/disabled.
"""
import os
import json
import shutil
import time

STATE_FILE = os.path.expanduser("~/.gemini/claude-router/account_lock_state.json")
ACCOUNTS_DIR = os.path.expanduser("~/.gemini/antigem-accounts")
LIVE_TOKEN_FILE = os.path.expanduser("~/.gemini/jetski-standalone-oauth-token")

def _build_default_accounts():
    """Auto-detect available AntiGem accounts on this device instead of hardcoding."""
    detected = list_available_accounts()
    accounts = []
    for idx, email in enumerate(detected, start=1):
        accounts.append({
            "id": f"acc_{idx}",
            "name": f"Account {idx}",
            "email": email,
            "models": []
        })
    return accounts

def load_state():
    if not os.path.exists(STATE_FILE):
        st = {"enabled": False, "accounts": _build_default_accounts(), "redirections": []}
        save_state(st)
        return st
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "enabled" not in data:
                data["enabled"] = False
            if "accounts" not in data:
                data["accounts"] = _build_default_accounts()
            if "redirections" not in data:
                data["redirections"] = []
            return data
    except Exception:
        return {"enabled": False, "accounts": _build_default_accounts(), "redirections": []}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def get_current_live_email():
    if not os.path.exists(LIVE_TOKEN_FILE):
        return ""
    try:
        with open(LIVE_TOKEN_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return (d.get("id_token_email") or d.get("email") or "").strip()
    except Exception:
        return ""

def list_available_accounts():
    res = []
    if os.path.isdir(ACCOUNTS_DIR):
        for fname in sorted(os.listdir(ACCOUNTS_DIR)):
            if fname.endswith(".json"):
                fpath = os.path.join(ACCOUNTS_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        acc_data = json.load(f)
                        email = acc_data.get("email") or acc_data.get("name") or fname[:-5]
                        res.append(email)
                except Exception:
                    pass
    return res

def normalize_model_family(model_name):
    """
    Distinguishes specific model variants cleanly:
    - Gemini 4 Neon (XHigh) vs regular Gemini 4 Neon
    - Gemini 4 Hydrogen (XHigh) vs regular Gemini 4 Hydrogen
    - Gemini 3.8 Flash (Low/Med/High) -> gemini-3.8-flash
    - Claude Opus 5.5, Claude Sonnet 5.5, GPT-OSS 120B, Gemini 4 Argon, etc.
    """
    if not model_name:
        return ""
    m = model_name.lower().strip()
    if "/" in m:
        m = m.split("/")[-1]

    # Neon: Check XHigh explicitly first!
    if "neon" in m:
        if "xhigh" in m or "x-high" in m:
            return "gemini-4-neon-xhigh"
        return "gemini-4-neon"

    # Hydrogen: Check XHigh explicitly first!
    if "hydrogen" in m or "hydr" in m:
        if "xhigh" in m or "x-high" in m:
            return "gemini-4-hydrogen-xhigh"
        return "gemini-4-hydrogen"

    # Gemini 3.8 Flash
    if "3.8-flash" in m or "3-8-flash" in m or "3.8 flash" in m:
        return "gemini-3.8-flash"

    # Claude models
    if "opus" in m:
        return "claude-opus-4.6"
    if "sonnet" in m:
        return "claude-sonnet-4.6"

    # GPT-OSS
    if "gpt-oss" in m:
        return "gpt-oss-120b"

    # Argon
    if "argon" in m:
        if "orchestrator" in m:
            return "orchestrator-argon"
        return "gemini-4-argon"

    # Orchestrator Neon
    if "orchestrator" in m:
        return "orchestrator-neon"

    # Carbon
    if "carbon" in m:
        return "gemini-4-carbon"

    return m

def resolve_effective_model(model_name, state=None):
    """
    Checks if a redirection profile matches the requested model.
    Supports exact match first, then normalized family match.
    If redirected, returns (effective_model, was_redirected).
    """
    if state is None:
        state = load_state()
    if state.get("redirections_enabled", True) is False:
        return model_name, False
    req_clean = model_name.strip().lower() if model_name else ""
    norm_req = normalize_model_family(model_name)
    
    # Pass 1: Exact / case-insensitive check
    for r in state.get("redirections", []):
        if r.get("enabled", True) and r.get("to_model"):
            from_m = (r.get("from_model") or "").strip().lower()
            if from_m == req_clean:
                return r.get("to_model"), True

    # Pass 2: Family normalized check
    for r in state.get("redirections", []):
        if r.get("enabled", True) and r.get("to_model"):
            if normalize_model_family(r.get("from_model")) == norm_req:
                return r.get("to_model"), True

    return model_name, False

def find_bound_account_for_model(model_name, state=None):
    if state is None:
        state = load_state()
    if not state.get("enabled", False):
        return None
    req_clean = model_name.strip().lower() if model_name else ""
    fam = normalize_model_family(model_name)

    # Pass 0: Direct Model -> Profile Account redirection rules (highest priority)
    if state.get("redirections_enabled", True) is not False:
        for r in state.get("redirections", []):
            if r.get("enabled", True) and r.get("to_account"):
                from_m = (r.get("from_model") or "").strip().lower()
                if from_m == req_clean:
                    return r.get("to_account")
        for r in state.get("redirections", []):
            if r.get("enabled", True) and r.get("to_account"):
                if normalize_model_family(r.get("from_model")) == fam:
                    return r.get("to_account")

    # Pass 1: Exact match with models configured in account
    for acc in state.get("accounts", []):
        for m in acc.get("models", []):
            if m.strip().lower() == req_clean:
                return acc.get("email")

    # Pass 2: Normalized family match
    for acc in state.get("accounts", []):
        for m in acc.get("models", []):
            if normalize_model_family(m) == fam:
                return acc.get("email")
    return None

def switch_to_account(target_email):
    current_email = get_current_live_email()
    if current_email.lower() == target_email.lower():
        return True, f"Already active: {target_email}"
    
    target_file = os.path.join(ACCOUNTS_DIR, f"{target_email}.json")
    if not os.path.exists(target_file):
        return False, f"Account file not found: {target_file}"
    
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        token_payload = data.get("token", data)
        if isinstance(token_payload, dict) and "writer_id" in token_payload:
            token_payload = json.loads(json.dumps(token_payload))
            del token_payload["writer_id"]
            
        with open(LIVE_TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(token_payload, f, indent=2)
            
        return True, f"Swapped active Google token to {target_email}"
    except Exception as e:
        return False, f"Failed to switch account: {e}"

def handle_redirection_switch_only(requested_model, state=None):
    """
    If an active Redirection rule matches requested_model, switches the active
    Google account immediately and signals the proxy to halt the request (0 quota).
    Returns: (matched: bool, account_name: str, account_email: str, status_msg: str)
    """
    if state is None:
        state = load_state()
    if not state.get("enabled", False):
        return False, "", "", ""
    if state.get("redirections_enabled", True) is False:
        return False, "", "", ""

    req_clean = requested_model.strip().lower() if requested_model else ""
    fam = normalize_model_family(requested_model)
    matched_rule = None

    for r in state.get("redirections", []):
        if r.get("enabled", True) and r.get("to_account") and r.get("to_account") != "__BLOCK__":
            from_m = (r.get("from_model") or "").strip().lower()
            if from_m == req_clean:
                matched_rule = r
                break

    if not matched_rule:
        for r in state.get("redirections", []):
            if r.get("enabled", True) and r.get("to_account") and r.get("to_account") != "__BLOCK__":
                if normalize_model_family(r.get("from_model")) == fam:
                    matched_rule = r
                    break

    if not matched_rule:
        return False, "", "", ""

    target_email = matched_rule.get("to_account", "")
    target_name = matched_rule.get("to_account_name") or target_email
    ok, msg = switch_to_account(target_email)
    return True, target_name, target_email, msg

def check_and_enforce_binding(requested_model):
    state = load_state()
    if not state.get("enabled", False):
        return False, "Feature OFF"
    
    # 1. Check if model is redirected!
    eff_model, redirected = resolve_effective_model(requested_model, state)
    
    # 2. Find bound account for the effective target model
    target_email = find_bound_account_for_model(eff_model, state)
    if not target_email:
        # Fallback to requested model if no bound acc found for target
        target_email = find_bound_account_for_model(requested_model, state)
        
    if not target_email:
        return False, f"No bound account for model '{requested_model}' (effective: '{eff_model}')"
    if target_email == "__BLOCK__":
        return False, f"BLOCKED: Model '{requested_model}' is blocked by Redirection rule"
    
    swapped, msg = switch_to_account(target_email)
    if redirected:
        msg = f"[Redirected {requested_model} -> {eff_model}] {msg}"
    return swapped, msg

if __name__ == "__main__":
    st = load_state()
    print("Account Lock State:", st)
    print("Current Live Email:", get_current_live_email())
    print("Available Accounts:", list_available_accounts())

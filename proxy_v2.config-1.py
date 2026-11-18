#!/usr/bin/env python3
import json
import os
import sys
import time
import socket
import threading
import urllib.request
import importlib.util

# Force IPv4 resolution to prevent Termux [Errno 104] Connection reset by peer
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(*args, **kwargs):
    responses = orig_getaddrinfo(*args, **kwargs)
    ipv4_responses = [r for r in responses if r[0] == socket.AF_INET]
    return ipv4_responses if ipv4_responses else responses
socket.getaddrinfo = getaddrinfo_ipv4

PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8999
STATUS_FILE = os.path.expanduser("~/.gemini/proxy/active_status.json")
CONFIG_FILE = os.path.expanduser("~/.gemini/claude-router/config.json")
LOG_FILE = os.path.expanduser("~/.gemini/claude-router/proxy_v2.log")
DASHBOARD_HTML_FILE = os.path.expanduser("~/.gemini/claude-router/dashboard.html")

config_lock = threading.Lock()

def _load_module_to_globals(filename, target_globals):
    filepath = os.path.join(os.path.dirname(__file__), filename)
    mod_name = filename.replace('.', '_').replace('-', '_')
    spec = importlib.util.spec_from_file_location(mod_name, filepath)
    mod = importlib.util.module_from_spec(spec)
    for k, v in target_globals.items():
        if not k.startswith('__'):
            setattr(mod, k, v)
    spec.loader.exec_module(mod)
    for k in dir(mod):
        if not k.startswith('__'):
            target_globals[k] = getattr(mod, k)
    return mod

# Modular live telemetry & cooldown store (gemini.md Rule 2: 400-500 line limit)
_config_live_mod = _load_module_to_globals("proxy_v2.config_live-1.py", globals())

def load_proxy_config():
    """Load config from JSON file with safe fallbacks and automatic key deduplication."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # Automatic key deduplication safeguard across all providers
            if isinstance(cfg, dict) and "providers" in cfg and isinstance(cfg["providers"], dict):
                for p_data in cfg["providers"].values():
                    if isinstance(p_data, dict) and "keys" in p_data and isinstance(p_data["keys"], list):
                        p_data["keys"] = list(dict.fromkeys(k.strip() for k in p_data["keys"] if isinstance(k, str) and k.strip()))
            return cfg
        except Exception as e:
            sys.stderr.write(f"[Config] Error reading {CONFIG_FILE}: {e}\n")
    return {"active_provider": "coarena", "providers": {}}

def sync_to_claude_settings(cfg):
    """Automatically syncs enabled (ON) providers and models to Claude Code UI dropdown (~/.claude/agy_providers.json)."""
    try:
        claude_dir = os.path.expanduser("~/.claude")
        if not os.path.exists(claude_dir):
            return
        agy_providers_path = os.path.join(claude_dir, "agy_providers.json")
        all_providers = cfg.get("providers", {})
        routed = cfg.get("routed_providers", [])
        ordered_ids = [p for p in routed if p in all_providers] + [p for p in all_providers if p not in routed]

        providers_out = []
        for p_id in ordered_ids:
            p_info = all_providers[p_id]
            if p_info.get("enabled", True) is False:
                continue
            base_url = f"http://127.0.0.1:{PORT}/{p_id}"
            models = p_info.get("models", [])
            def_m = p_info.get("default_model") or (models[0] if models else "")
            model_list = [{"id": m} for m in models]
            if not model_list and def_m:
                model_list = [{"id": def_m}]
            is_routed = p_id in routed
            route_tag = "🌐 Router" if is_routed else "🔒 Direct"
            mode_val = (p_info.get("mode") or "agentic").lower()
            mode_tag = "⚡ Agentic" if mode_val == "agentic" else "💡 Normal"
            keys_count = len(p_info.get('keys', []))

            p_entry = {
                "id": p_id,
                "name": f"{p_info.get('name', p_id)} [{route_tag} | {mode_tag}] ({keys_count} Keys)",
                "base_url": base_url,
                "api_key": "auto",
                "auth_mode": "bearer",
                "models": model_list
            }
            providers_out.append(p_entry)

        agy_data = {"providers": providers_out}

        # Inject Multi-Agent Teams directly into chat dropdown if any enabled teams exist
        teams = cfg.get("multi_agent_teams", {})
        enabled_teams = [t for t in teams.values() if t.get("enabled", True) is not False]
        if enabled_teams:
            team_models = []
            for t in enabled_teams:
                tid = t.get("id") or t.get("slug") or "team"
                tname = t.get("name", tid)
                members = t.get("members", [])
                m_labels = []
                for m in members:
                    p_id = m.get("provider", "")
                    p_obj = all_providers.get(p_id, {})
                    p_label = p_obj.get("name", p_id)
                    m_label = m.get("model", "").split("/")[-1]
                    m_labels.append(f"{p_label}:{m_label}")
                mix_summary = " + ".join(m_labels) if m_labels else "Mix"
                team_models.append({
                    "id": f"team:{tid}",
                    "name": f"🤖 {tname} [{mix_summary}]"
                })

            providers_out.insert(0, {
                "id": "multiagent",
                "name": "🤖 MULTI-AGENT TEAMS [⚡ Agentic Pipeline]",
                "base_url": f"http://127.0.0.1:{PORT}/multiagent",
                "api_key": "auto",
                "auth_mode": "bearer",
                "models": team_models
            })

        if os.path.exists(agy_providers_path):
            try:
                with open(agy_providers_path, "r", encoding="utf-8") as f:
                    cur = json.load(f)
                    if "sessions" in cur:
                        agy_data["sessions"] = cur["sessions"]
            except Exception:
                pass

        tmp_path = agy_providers_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(agy_data, f, indent=2)
        os.replace(tmp_path, agy_providers_path)
    except Exception as e:
        sys.stderr.write(f"[Claude Sync] Warning: Could not sync to Claude settings: {e}\n")

def save_proxy_config(cfg):
    """Save config safely to JSON file and sync to Claude Code UI dropdown with key deduplication."""
    with config_lock:
        try:
            if isinstance(cfg, dict) and "providers" in cfg and isinstance(cfg["providers"], dict):
                for p_data in cfg["providers"].values():
                    if isinstance(p_data, dict) and "keys" in p_data and isinstance(p_data["keys"], list):
                        p_data["keys"] = list(dict.fromkeys(k.strip() for k in p_data["keys"] if isinstance(k, str) and k.strip()))
            tmp = CONFIG_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            os.replace(tmp, CONFIG_FILE)
            sync_to_claude_settings(cfg)
            return True
        except Exception as e:
            sys.stderr.write(f"[Config] Error saving {CONFIG_FILE}: {e}\n")
            return False

def get_provider_keys(provider_id):
    """Dynamically get keys list for a provider."""
    cfg = load_proxy_config()
    p = cfg.get("providers", {}).get(provider_id, {})
    return p.get("keys", [])

# Provider key accessors
def get_coarena_keys():
    return get_provider_keys("coarena")

def get_agentrouter_key():
    keys = get_provider_keys("agentrouter")
    return keys[0] if keys else ""

def get_openrouter_keys():
    return get_provider_keys("openrouter")

def get_groq_keys():
    return get_provider_keys("groq")

def get_gonkabroker_keys():
    return get_provider_keys("gonkabroker")

current_coarena_idx = 0
current_openrouter_idx = 0
current_groq_idx = 0
current_gonka_idx = 0

def get_active_state():
    """Return the shared live active state across all dynamic module loads."""
    with _LIVE_STORE.lock:
        return dict(_LIVE_STORE.active_state)

def save_active_state(server, model, account, input_tokens=0, output_tokens=0, tok_per_sec=0.0, latency_ms=0):
    new_state = {
        "server": server,
        "model": model,
        "account": account,
        "tag": f"{server} - {model}",
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "tok_per_sec": round(float(tok_per_sec or 0.0), 1),
        "latency_ms": int(latency_ms or 0),
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with _LIVE_STORE.lock:
        _LIVE_STORE.active_state = new_state
        _LIVE_STORE.seq += 1
    global active_state
    active_state = new_state
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(new_state, f, indent=2)
    except Exception:
        pass

# Only set default initial state if not already set by an active request
if not getattr(_LIVE_STORE, "active_state", None) or _LIVE_STORE.active_state.get("server") == "Coarena":
    save_active_state("Coarena", "gemini-4-carbon", "Coarena Account #1")

# Initial startup sync to Claude settings
sync_to_claude_settings(load_proxy_config())

# Recovery & failover tracking
fallback_to_agentrouter = False
last_fallback_time = 0
RECOVERY_INTERVAL = 300  # 5 minutes (300s)

def test_coarena_alive():
    """Test if Coarena is alive with gemini-4-carbon or gemini-3-8-flash"""
    keys = get_coarena_keys()
    for m in ["gemini-4-carbon", "gemini-3-8-flash"]:
        body = json.dumps({'model': m, 'messages': [{'role': 'user', 'content': 'ping'}], 'max_tokens': 10}).encode('utf-8')
        for k in keys:
            req = urllib.request.Request('https://coarena.ai/api/v1/messages', data=body, headers={
                'Authorization': f'Bearer {k}',
                'x-api-key': k,
                'Content-Type': 'application/json'
            })
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        return ("Coarena", m)
            except Exception:
                continue
    return None

def test_groq_alive():
    """Test if Groq is alive with gpt-oss-120b or qwen3.8-27b"""
    keys = get_groq_keys()
    for m in ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]:
        body = json.dumps({'model': m, 'messages': [{'role': 'user', 'content': 'ping'}], 'max_tokens': 10}).encode('utf-8')
        for k in keys:
            req = urllib.request.Request('https://api.groq.com/openai/v1/chat/completions', data=body, headers={
                'Authorization': f'Bearer {k}',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            })
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        return ("Groq", m)
            except Exception:
                continue
    return None

def test_openrouter_alive():
    """Test if OpenRouter is alive with claude-haiku-5.5 or claude-sonnet-5"""
    keys = get_openrouter_keys()
    for m in ["anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5"]:
        body = json.dumps({'model': m, 'messages': [{'role': 'user', 'content': 'ping'}], 'max_tokens': 10}).encode('utf-8')
        for k in keys:
            req = urllib.request.Request('https://openrouter.ai/api/v1/messages', data=body, headers={
                'Authorization': f'Bearer {k}',
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01',
                'HTTP-Referer': 'https://antigravity.dev',
                'X-Title': 'Antigravity IDE'
            })
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        return ("OpenRouter", m)
            except Exception:
                continue
    return None

def test_gonkabroker_alive():
    """Test if GonkaBroker is alive with zai-org/GLM-5.3-Flash"""
    keys = get_gonkabroker_keys()
    m = "zai-org/GLM-5.3-Flash"
    body = json.dumps({'model': m, 'messages': [{'role': 'user', 'content': 'ping'}], 'max_tokens': 10}).encode('utf-8')
    for k in keys:
        req = urllib.request.Request('https://proxy.gonkabroker.com/v1/messages', data=body, headers={
            'x-api-key': k,
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01'
        })
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return ("GonkaBroker", m)
        except Exception:
            continue
    return None

def recovery_monitor_loop():
    """Background daemon that runs every 5 minutes when on AgentRouter fallback"""
    global fallback_to_agentrouter, last_fallback_time
    while True:
        time.sleep(15)
        if fallback_to_agentrouter and (time.time() - last_fallback_time >= RECOVERY_INTERVAL):
            sys.stderr.write("[Recovery Monitor] Checking servers sequentially: Coarena -> Groq -> OpenRouter -> GonkaBroker...\n")
            res = test_coarena_alive()
            if res:
                srv, mdl = res
                sys.stderr.write(f"[Recovery Monitor] Coarena is back online with {mdl}!\n")
                fallback_to_agentrouter = False
                save_active_state(srv, mdl, "Coarena Auto-Recovered")
                continue
            res = test_groq_alive()
            if res:
                srv, mdl = res
                sys.stderr.write(f"[Recovery Monitor] Groq is back online with {mdl}!\n")
                fallback_to_agentrouter = False
                save_active_state(srv, mdl, "Groq Auto-Recovered")
                continue
            res = test_openrouter_alive()
            if res:
                srv, mdl = res
                sys.stderr.write(f"[Recovery Monitor] OpenRouter is back online with {mdl}!\n")
                fallback_to_agentrouter = False
                save_active_state(srv, mdl, "OpenRouter Auto-Recovered")
                continue
            res = test_gonkabroker_alive()
            if res:
                srv, mdl = res
                sys.stderr.write(f"[Recovery Monitor] GonkaBroker is back online with {mdl}!\n")
                fallback_to_agentrouter = False
                save_active_state(srv, mdl, "GonkaBroker Auto-Recovered")
                continue
            last_fallback_time = time.time()

# Launch background recovery thread only once across module loads
if "_claude_router_recovery_started" not in sys.modules:
    sys.modules["_claude_router_recovery_started"] = True
    recovery_thread = threading.Thread(target=recovery_monitor_loop, daemon=True)
    recovery_thread.start()

MODEL_FALLBACKS = {
    "gemini-4-carbon": ["gemini-3-8-flash", "deepseek-v4-1-flash-1017"],
    "gemini-3-8-flash": ["gemini-4-carbon", "deepseek-v4-1-flash-1017"],
    "claude-sonnet-5-5": ["gemini-3-8-flash", "gemini-4-carbon", "deepseek-v4-1-flash-1017"],
    "claude-opus-5-5": ["gemini-3-8-flash", "gemini-4-carbon"],
    "claude-haiku-5-5": ["gemini-3-8-flash", "deepseek-v4-1-flash-1017"],
}

_config_live_mod.load_proxy_config = load_proxy_config
_config_live_mod.get_active_state = get_active_state

import os
import json
import time
import subprocess
import urllib.request
import urllib.error
import threading

ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(ROUTER_DIR, "models")
MODEL_FILENAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
MODEL_PATH = os.path.join(MODELS_DIR, MODEL_FILENAME)
MODEL_URL = "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"

LOCAL_SERVER_PORT = 8327
LOCAL_SERVER_URL = f"http://127.0.0.1:{LOCAL_SERVER_PORT}/v1/chat/completions"

# Preference config: default mode is 'online'
PREF_FILE = os.path.join(ROUTER_DIR, "fox_pref.json")

def load_fox_mode():
    if os.path.exists(PREF_FILE):
        try:
            with open(PREF_FILE, 'r') as f:
                return json.load(f).get("engine_mode")
        except Exception:
            pass
    # If local model is installed and ready, default to local on 3-tap!
    has_model = os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 300 * 1024 * 1024
    has_llama = subprocess.call(["command", "-v", "llama-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True) == 0
    if has_model and has_llama:
        return "local"
    return "online"

def save_fox_mode(mode):
    try:
        with open(PREF_FILE, 'w') as f:
            json.dump({"engine_mode": mode}, f)
    except Exception:
        pass

setup_progress = {
    "status": "idle", # idle, installing, downloading, starting, ready, error
    "step": "",
    "percent": 0,
    "error_message": ""
}

def check_local_setup_status():
    has_llama = subprocess.call(["command", "-v", "llama-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True) == 0
    has_model = os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 300 * 1024 * 1024
    
    server_running = False
    if has_llama and has_model:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{LOCAL_SERVER_PORT}/health")
            with urllib.request.urlopen(req, timeout=1.5) as r:
                server_running = (r.status == 200)
        except Exception:
            server_running = False

    return {
        "installed": (has_llama and has_model),
        "has_llama": has_llama,
        "has_model": has_model,
        "running": server_running,
        "mode": load_fox_mode(),
        "port": LOCAL_SERVER_PORT,
        "progress": setup_progress,
        "model_file_size_mb": round(os.path.getsize(MODEL_PATH) / (1024 * 1024), 1) if os.path.exists(MODEL_PATH) else 0,
        "lora_installed": os.path.exists(os.path.join(MODELS_DIR, "fox_lora.gguf"))
    }

def start_llama_server_background():
    if not os.path.exists(MODEL_PATH):
        return False
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{LOCAL_SERVER_PORT}/health")
        with urllib.request.urlopen(req, timeout=1.5) as r:
            if r.status == 200:
                return True
    except Exception:
        pass

    cmd = [
        "llama-server",
        "-m", MODEL_PATH,
        "--port", str(LOCAL_SERVER_PORT),
        "--host", "127.0.0.1",
        "-c", "2048",
        "-t", "4",
        "--log-disable"
    ]
    lora_path = os.path.join(MODELS_DIR, "fox_lora.gguf")
    if not os.path.exists(lora_path):
        lora_path = os.path.join(MODELS_DIR, "fox_bengali_lora.gguf")
    if os.path.exists(lora_path):
        cmd.extend(["--lora", lora_path])
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(12):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{LOCAL_SERVER_PORT}/health", timeout=1) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
    except Exception as e:
        setup_progress["error_message"] = str(e)
    return False

def _run_installer_thread():
    global setup_progress
    setup_progress["status"] = "installing"
    setup_progress["step"] = "Checking llama.cpp engine..."
    setup_progress["percent"] = 10

    # 1. Install llama.cpp if missing
    has_llama = subprocess.call(["command", "-v", "llama-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True) == 0
    if not has_llama:
        setup_progress["step"] = "Installing llama.cpp via pkg (takes 1-2 mins)..."
        setup_progress["percent"] = 25
        res = subprocess.run(["pkg", "install", "-y", "llama.cpp"], capture_output=True, text=True)
        if res.returncode != 0:
            setup_progress["status"] = "error"
            setup_progress["error_message"] = "Failed to install llama.cpp: " + (res.stderr or res.stdout)[:200]
            return

    # 2. Download Model if missing
    os.makedirs(MODELS_DIR, exist_ok=True)
    if not (os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 300 * 1024 * 1024):
        setup_progress["status"] = "downloading"
        setup_progress["step"] = "Downloading Qwen2.5-0.5B (~320MB)..."
        setup_progress["percent"] = 40

        tmp_dest = MODEL_PATH + ".part"
        try:
            req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "ClaudeRouter/2.0"})
            with urllib.request.urlopen(req, timeout=600) as resp:
                total_size = int(resp.headers.get("content-length", 320 * 1024 * 1024))
                downloaded = 0
                chunk_size = 1024 * 512
                with open(tmp_dest, "wb") as f_out:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        downloaded += len(chunk)
                        pct = int(40 + (downloaded / total_size) * 50)
                        setup_progress["percent"] = min(90, pct)
                        mb = downloaded / (1024 * 1024)
                        setup_progress["step"] = f"Downloading Qwen2.5 ({mb:.1f}MB / 320MB)..."

            os.replace(tmp_dest, MODEL_PATH)
        except Exception as e:
            if os.path.exists(tmp_dest):
                try: os.remove(tmp_dest)
                except: pass
            setup_progress["status"] = "error"
            setup_progress["error_message"] = f"Download failed: {str(e)}"
            return

    # 3. Starting Server on Port 8327
    setup_progress["status"] = "starting"
    setup_progress["step"] = f"Starting local neural engine on port {LOCAL_SERVER_PORT}..."
    setup_progress["percent"] = 95
    ok = start_llama_server_background()

    if ok:
        setup_progress["status"] = "ready"
        setup_progress["step"] = "Qwen2.5-0.5B Local Brain is LIVE!"
        setup_progress["percent"] = 100
        save_fox_mode("local") # automatically activate local mode once setup finishes!
    else:
        setup_progress["status"] = "error"
        setup_progress["error_message"] = f"Could not verify llama-server startup on port {LOCAL_SERVER_PORT}"

def handle_fox_local_installer(handler, raw_body):
    if handler.path == "/api/ui/fox-local/status":
        st = check_local_setup_status()
        resp = json.dumps({"status": "ok", "data": st}).encode('utf-8')
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.send_header('Content-Length', str(len(resp)))
        handler.end_headers()
        handler.wfile.write(resp)
        return True

    if handler.path == "/api/ui/fox-local/set-mode":
        try:
            data = json.loads(raw_body.decode('utf-8'))
            m = data.get("mode", "online")
            if m not in ("online", "local"):
                m = "online"
            save_fox_mode(m)
            # If switching to local, make sure server is up
            if m == "local":
                start_llama_server_background()

            resp = json.dumps({"status": "ok", "mode": m}).encode()
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
            handler.end_headers()
            handler.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())
            return True

    if handler.path == "/api/ui/fox-local/start-install":
        st = check_local_setup_status()
        if setup_progress["status"] in ("installing", "downloading", "starting"):
            resp = json.dumps({"status": "busy", "message": "Installation already in progress"}).encode()
        else:
            setup_progress["status"] = "starting"
            setup_progress["percent"] = 5
            setup_progress["error_message"] = ""
            t = threading.Thread(target=_run_installer_thread, daemon=True)
            t.start()
            resp = json.dumps({"status": "ok", "message": "Installation initiated"}).encode()

        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.send_header('Content-Length', str(len(resp)))
        handler.end_headers()
        handler.wfile.write(resp)
        return True

    if handler.path == "/api/ui/fox-local/remove":
        try:
            # 1. Stop server if running
            pkill_res = subprocess.run(["pkill", "-9", "-f", f"llama-server.*{LOCAL_SERVER_PORT}"], capture_output=True)
            # 2. Switch mode back to online
            save_fox_mode("online")
            # 3. Remove base model file
            removed_model = False
            if os.path.exists(MODEL_PATH):
                try:
                    os.remove(MODEL_PATH)
                    removed_model = True
                except Exception as e:
                    print(f"Error removing model file: {e}")
            if os.path.exists(MODEL_PATH + ".part"):
                try: os.remove(MODEL_PATH + ".part")
                except: pass

            setup_progress["status"] = "idle"
            setup_progress["percent"] = 0
            setup_progress["step"] = ""
            setup_progress["error_message"] = ""

            st = check_local_setup_status()
            resp = json.dumps({"status": "ok", "message": "Local brain model removed and switched to Online mode", "data": st}).encode('utf-8')
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
            err = json.dumps({"status": "error", "message": str(e)}).encode('utf-8')
            handler.send_header('Content-Length', str(len(err)))
            handler.end_headers()
            handler.wfile.write(err)
            return True

    return False

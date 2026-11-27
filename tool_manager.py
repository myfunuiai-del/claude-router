import json
import os
import signal
import subprocess
import threading
import time

ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(ROUTER_DIR, "tools_registry.json")

# In-memory tracker for async installations
_INSTALL_JOBS = {}
_JOBS_LOCK = threading.Lock()


def _expand(path_str):
    return os.path.expanduser(path_str)


def load_registry():
    if not os.path.exists(REGISTRY_PATH):
        return []
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("tools", [])
    except Exception:
        return []


def get_tool(tool_id):
    for t in load_registry():
        if t.get("id") == tool_id:
            return t
    return None


def _is_running(pattern):
    try:
        res = subprocess.run(
            ["pgrep", "-f", pattern],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        pids = [p.strip() for p in res.stdout.splitlines() if p.strip()]
        return (True, int(pids[0])) if pids else (False, None)
    except Exception:
        return (False, None)


def get_tool_status(tool):
    install_dir = _expand(tool.get("install_dir", ""))
    subdir = tool.get("plugin_subdir", "")
    check_dir = os.path.join(install_dir, subdir) if subdir else install_dir
    installed = os.path.exists(check_dir) and os.path.isdir(check_dir)
    running, pid = _is_running(tool.get("process_pattern", tool.get("id")))
    return {
        "id": tool.get("id"),
        "name": tool.get("name"),
        "description": tool.get("description"),
        "repo": tool.get("repo"),
        "default_port": tool.get("default_port", 1337),
        "installed": installed,
        "running": running,
        "pid": pid,
        "install_dir": install_dir,
        "provider_template": tool.get("provider_template", {}),
    }


def list_tools_with_status():
    return [get_tool_status(t) for t in load_registry()]


def get_install_plan(tool_id):
    tool = get_tool(tool_id)
    if not tool:
        return {"ok": False, "error": f"Tool '{tool_id}' not found."}

    install_dir = _expand(tool.get("install_dir", ""))
    subdir = tool.get("plugin_subdir", "")
    check_dir = os.path.join(install_dir, subdir) if subdir else install_dir

    if os.path.exists(check_dir):
        return {"ok": False, "error": f"{tool_id} is already installed."}

    # Check repo size / packages
    items = []
    est_mb = 0.0

    if not os.path.exists(os.path.join(install_dir, ".git")):
        items.append("Repository: Crouter-Plugin (GitHub) (~4.0 MB)")
        est_mb += 4.0
    else:
        items.append(f"Plugin module: {subdir or tool_id} (from local Git) (~3.8 MB)")
        est_mb += 3.8

    # Check missing python packages if requirements-min.txt exists or default list
    required_pkgs = ["requests", "aiohttp", "certifi", "nest-asyncio2", "werkzeug", "python-multipart", "beautifulsoup4"]
    try:
        res = subprocess.run(["python3", "-m", "pip", "list", "--format=json"], stdout=subprocess.PIPE, text=True, timeout=5)
        installed_pkgs = {p["name"].lower() for p in json.loads(res.stdout)}
    except Exception:
        installed_pkgs = set()

    missing_pkgs = [p for p in required_pkgs if p.lower() not in installed_pkgs]
    if missing_pkgs:
        pkg_mb = round(len(missing_pkgs) * 1.2, 1)
        items.append(f"Python packages ({len(missing_pkgs)}): {', '.join(missing_pkgs)} (~{pkg_mb} MB)")
        est_mb += pkg_mb
    else:
        items.append("Python dependencies: All core packages already satisfied (0 MB)")

    items.append(f"CLI Shortcut: ~/.local/bin/{tool_id.replace('-api', 'api')} (< 0.1 MB)")

    return {
        "ok": True,
        "tool_id": tool_id,
        "name": tool.get("name"),
        "estimated_size_mb": round(est_mb, 1),
        "items": items
    }


def _cleanup_partial_install(tool):
    install_dir = _expand(tool.get("install_dir", ""))
    subdir = tool.get("plugin_subdir", "")
    target_dir = os.path.join(install_dir, subdir) if subdir else install_dir
    if os.path.exists(target_dir):
        subprocess.run(["rm", "-rf", target_dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Also remove symlink if created
    uninstall_cmd = tool.get("commands", {}).get("uninstall")
    if uninstall_cmd:
        subprocess.run(uninstall_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_async_install(tool_id):
    tool = get_tool(tool_id)
    if not tool:
        return {"ok": False, "error": f"Tool '{tool_id}' not found."}

    with _JOBS_LOCK:
        existing = _INSTALL_JOBS.get(tool_id)
        if existing and existing.get("status") == "running":
            return {"ok": True, "message": "Installation already in progress."}

        _INSTALL_JOBS[tool_id] = {
            "status": "running",
            "progress": 5,
            "stage": "Initializing installation...",
            "logs": ["[*] Starting installation..."],
            "proc": None,
            "cancelled": False,
        }

    def _worker():
        cmd = tool.get("commands", {}).get("install", "")
        if not cmd:
            with _JOBS_LOCK:
                _INSTALL_JOBS[tool_id]["status"] = "error"
                _INSTALL_JOBS[tool_id]["stage"] = "No install command defined."
            return

        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid,
            )
            with _JOBS_LOCK:
                _INSTALL_JOBS[tool_id]["proc"] = proc
                _INSTALL_JOBS[tool_id]["progress"] = 15
                _INSTALL_JOBS[tool_id]["stage"] = "Fetching files from GitHub..."

            for line in iter(proc.stdout.readline, ""):
                with _JOBS_LOCK:
                    if _INSTALL_JOBS[tool_id]["cancelled"]:
                        break
                    clean_line = line.strip()
                    if clean_line:
                        logs = _INSTALL_JOBS[tool_id]["logs"]
                        logs.append(clean_line)
                        if len(logs) > 40:
                            logs.pop(0)

                        # Heuristic progress updates
                        cur_p = _INSTALL_JOBS[tool_id]["progress"]
                        low = clean_line.lower()
                        if "cloning" in low or "fetching" in low or "receiving" in low:
                            _INSTALL_JOBS[tool_id]["progress"] = max(cur_p, 35)
                            _INSTALL_JOBS[tool_id]["stage"] = "Downloading repository files..."
                        elif "installing g4f-api" in low or "symlinked" in low:
                            _INSTALL_JOBS[tool_id]["progress"] = max(cur_p, 55)
                            _INSTALL_JOBS[tool_id]["stage"] = "Setting up CLI & shortcuts..."
                        elif "collecting" in low or "downloading" in low:
                            _INSTALL_JOBS[tool_id]["progress"] = min(85, max(cur_p + 5, 65))
                            _INSTALL_JOBS[tool_id]["stage"] = "Installing Python dependencies..."
                        elif "successfully installed" in low or "requirement already satisfied" in low:
                            _INSTALL_JOBS[tool_id]["progress"] = max(cur_p, 90)
                            _INSTALL_JOBS[tool_id]["stage"] = "Finalizing installation..."
                        elif "installation complete" in low:
                            _INSTALL_JOBS[tool_id]["progress"] = 100
                            _INSTALL_JOBS[tool_id]["stage"] = "Installation complete!"

            proc.wait()

            with _JOBS_LOCK:
                if _INSTALL_JOBS[tool_id]["cancelled"]:
                    _INSTALL_JOBS[tool_id]["status"] = "cancelled"
                    _INSTALL_JOBS[tool_id]["stage"] = "Cancelled & cleaned up."
                    _INSTALL_JOBS[tool_id]["progress"] = 0
                elif proc.returncode == 0:
                    _INSTALL_JOBS[tool_id]["status"] = "done"
                    _INSTALL_JOBS[tool_id]["progress"] = 100
                    _INSTALL_JOBS[tool_id]["stage"] = "Installed successfully!"
                else:
                    _INSTALL_JOBS[tool_id]["status"] = "error"
                    _INSTALL_JOBS[tool_id]["stage"] = f"Failed (exit code {proc.returncode})"
                    _cleanup_partial_install(tool)
        except Exception as e:
            with _JOBS_LOCK:
                _INSTALL_JOBS[tool_id]["status"] = "error"
                _INSTALL_JOBS[tool_id]["stage"] = f"Error: {str(e)}"
                _INSTALL_JOBS[tool_id]["logs"].append(f"[-] Error: {str(e)}")
                _cleanup_partial_install(tool)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return {"ok": True, "message": "Installation started."}


def get_install_progress(tool_id):
    with _JOBS_LOCK:
        job = _INSTALL_JOBS.get(tool_id)
        if not job:
            return {"ok": True, "status": "idle", "progress": 0, "stage": "", "logs": []}
        return {
            "ok": True,
            "status": job["status"],
            "progress": job["progress"],
            "stage": job["stage"],
            "logs": list(job["logs"]),
        }


def cancel_install(tool_id):
    tool = get_tool(tool_id)
    with _JOBS_LOCK:
        job = _INSTALL_JOBS.get(tool_id)
        if not job or job.get("status") != "running":
            return {"ok": False, "error": "No active installation to cancel."}
        job["cancelled"] = True
        job["status"] = "cancelled"
        job["stage"] = "Cancelling & cleaning up partial downloads..."
        proc = job.get("proc")
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    if tool:
        _cleanup_partial_install(tool)

    with _JOBS_LOCK:
        if tool_id in _INSTALL_JOBS:
            _INSTALL_JOBS[tool_id]["stage"] = "Installation cancelled and partial files deleted."
            _INSTALL_JOBS[tool_id]["progress"] = 0

    return {"ok": True, "message": "Installation cancelled and partial files cleaned up."}


def run_tool_action(tool_id, action, port=None):
    tool = get_tool(tool_id)
    if not tool:
        return {"ok": False, "error": f"Tool '{tool_id}' not found in registry."}

    cmds = tool.get("commands", {})
    target_port = port or tool.get("default_port", 1337)
    install_dir = _expand(tool.get("install_dir", ""))
    subdir = tool.get("plugin_subdir", "")
    check_dir = os.path.join(install_dir, subdir) if subdir else install_dir

    if action == "status":
        return {"ok": True, "status": get_tool_status(tool)}

    if action == "install_plan":
        return get_install_plan(tool_id)

    if action == "install_start":
        return start_async_install(tool_id)

    if action == "install_cancel":
        return cancel_install(tool_id)

    if action == "install":
        if os.path.exists(check_dir):
            return {"ok": True, "message": f"{tool_id} is already installed."}
        cmd = cmds.get("install")
        if not cmd:
            return {"ok": False, "error": "No install command defined."}
        res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            return {"ok": True, "message": f"{tool_id} installed successfully.", "output": res.stdout[-500:]}
        return {"ok": False, "error": res.stderr[-500:] or res.stdout[-500:]}

    if action == "uninstall":
        stop_cmd = cmds.get("stop")
        if stop_cmd:
            subprocess.run(stop_cmd, shell=True)
        cmd = cmds.get("uninstall")
        if not cmd:
            return {"ok": False, "error": "No uninstall command defined."}
        res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            return {"ok": True, "message": f"{tool_id} uninstalled successfully."}
        return {"ok": False, "error": res.stderr[-500:]}

    if action == "start":
        if not os.path.exists(check_dir):
            return {"ok": False, "error": f"{tool_id} is not installed. Please install it first."}
        running, pid = _is_running(tool.get("process_pattern", tool_id))
        if running:
            return {"ok": True, "message": f"{tool_id} is already running (PID: {pid}).", "pid": pid}
        cmd = cmds.get("start", "").replace("{port}", str(target_port))
        if not cmd:
            return {"ok": False, "error": "No start command defined."}
        subprocess.Popen(cmd, shell=True, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        running, pid = _is_running(tool.get("process_pattern", tool_id))
        if running:
            return {"ok": True, "message": f"{tool_id} started on port {target_port}.", "pid": pid, "port": target_port}
        return {"ok": False, "error": f"Failed to start {tool_id}."}

    if action == "stop":
        cmd = cmds.get("stop")
        if not cmd:
            return {"ok": False, "error": "No stop command defined."}
        subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return {"ok": True, "message": f"{tool_id} stopped."}

    if action == "check":
        if not os.path.exists(os.path.join(install_dir, ".git")):
            return {"ok": False, "error": f"{tool_id} is not a git repository."}
        subprocess.run(["git", "-C", install_dir, "fetch", "origin", "main"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        local = subprocess.run(["git", "-C", install_dir, "rev-parse", "HEAD"], stdout=subprocess.PIPE, text=True).stdout.strip()
        remote = subprocess.run(["git", "-C", install_dir, "rev-parse", "origin/main"], stdout=subprocess.PIPE, text=True).stdout.strip()
        update_available = (local != remote) and bool(local) and bool(remote)
        return {
            "ok": True,
            "update_available": update_available,
            "local_commit": local[:7],
            "remote_commit": remote[:7],
            "message": "New update available!" if update_available else "Already up to date."
        }

    if action == "update":
        if not os.path.exists(install_dir):
            return {"ok": False, "error": f"{tool_id} is not installed."}
        was_running, _ = _is_running(tool.get("process_pattern", tool_id))
        if was_running:
            run_tool_action(tool_id, "stop")
        cmd = cmds.get("update")
        res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            return {"ok": False, "error": res.stderr[-500:]}
        if was_running:
            run_tool_action(tool_id, "start", port=target_port)
        return {"ok": True, "message": f"{tool_id} updated successfully!", "output": res.stdout[-300:]}

    return {"ok": False, "error": f"Unknown action: {action}"}

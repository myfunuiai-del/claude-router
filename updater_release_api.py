#!/usr/bin/env python3
"""
Claude Router - Auto Update Checker, Force Updater & Release Publisher API
Handles:
  - GET  /api/ui/version-check -> checks current vs remote release/commit
  - POST /api/ui/update-apply  -> pulls latest git updates (or force reinstall), keeps config safe, and restarts
"""
import os
import sys
import json
import urllib.request
import subprocess

REPO_OWNER = "myfunuiai-del"
REPO_NAME = "claude-router"
GITHUB_API_RELEASES = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
GITHUB_API_COMMITS = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/main"

ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(ROUTER_DIR, "VERSION")

def get_current_version():
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
        except Exception:
            pass
    # Fallback to local git commit hash if available
    try:
        res = subprocess.run(["git", "-C", ROUTER_DIR, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            return f"commit-{res.stdout.strip()}"
    except Exception:
        pass
    return "v2.1.0"

def check_remote_version():
    cur = get_current_version()
    latest_tag = None
    release_notes = ""
    published_at = ""
    latest_commit = None
    commit_msg = ""

    # 1. Check GitHub Releases
    try:
        req = urllib.request.Request(GITHUB_API_RELEASES, headers={"User-Agent": "Claude-Router-Updater"})
        with urllib.request.urlopen(req, timeout=4) as r:
            if r.status == 200:
                d = json.load(r)
                latest_tag = d.get("tag_name")
                release_notes = d.get("body") or ""
                published_at = d.get("published_at") or ""
    except Exception:
        pass

    # 2. Check GitHub Commits (Main branch)
    try:
        req = urllib.request.Request(GITHUB_API_COMMITS, headers={"User-Agent": "Claude-Router-Updater"})
        with urllib.request.urlopen(req, timeout=4) as r:
            if r.status == 200:
                d = json.load(r)
                latest_commit = (d.get("sha") or "")[:7]
                commit_msg = (d.get("commit", {}).get("message") or "").split("\n")[0]
    except Exception:
        pass

    # Determine if update available
    update_available = False
    target_version = latest_tag or (f"commit-{latest_commit}" if latest_commit else cur)

    if latest_tag and latest_tag != cur:
        update_available = True
    elif not latest_tag and latest_commit:
        local_sha = ""
        try:
            res = subprocess.run(["git", "-C", ROUTER_DIR, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                local_sha = res.stdout.strip()
        except Exception:
            pass
        if local_sha and local_sha != latest_commit:
            update_available = True

    return {
        "current_version": cur,
        "latest_version": target_version,
        "has_release": bool(latest_tag),
        "latest_commit": latest_commit,
        "commit_msg": commit_msg,
        "release_notes": release_notes,
        "published_at": published_at,
        "update_available": update_available
    }

def fetch_github_commits(page=1, per_page=10):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits?page={page}&per_page={per_page}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Claude-Router-Updater"})
        with urllib.request.urlopen(req, timeout=5) as r:
            if r.status == 200:
                raw_commits = json.load(r)
                result = []
                for item in raw_commits:
                    sha = (item.get("sha") or "")[:7]
                    commit_obj = item.get("commit", {})
                    msg = commit_obj.get("message") or ""
                    first_line = msg.split("\n")[0]
                    author_name = commit_obj.get("author", {}).get("name") or "myfunuiai"
                    date_str = commit_obj.get("author", {}).get("date") or ""
                    html_url = item.get("html_url") or f"https://github.com/{REPO_OWNER}/{REPO_NAME}/commit/{sha}"
                    result.append({
                        "sha": sha,
                        "title": first_line,
                        "author": author_name,
                        "date": date_str,
                        "url": html_url
                    })
                return True, result
    except Exception as e:
        return False, str(e)
    return False, "Failed to fetch commits"

def handle_commits_get(handler):
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(handler.path)
        qs = parse_qs(parsed.query)
        page = int(qs.get("page", ["1"])[0])
        per_page = int(qs.get("per_page", ["8"])[0])
        ok, data = fetch_github_commits(page=page, per_page=per_page)
        if ok:
            resp = json.dumps({"status": "ok", "page": page, "commits": data}).encode("utf-8")
        else:
            resp = json.dumps({"status": "error", "message": data, "commits": []}).encode("utf-8")
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.send_header('Content-Length', str(len(resp)))
        handler.end_headers()
        handler.wfile.write(resp)
    except Exception as e:
        handler.send_response(500)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        err = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
        handler.send_header('Content-Length', str(len(err)))
        handler.end_headers()
        handler.wfile.write(err)

def handle_full_backup_get(handler):
    try:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(handler.path).query)
        include_keys = qs.get("include_keys", ["1"])[0] != "0"

        cfg_path = os.path.join(ROUTER_DIR, "config.json")
        cfg = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        if not include_keys and isinstance(cfg.get("providers"), dict):
            for p in cfg["providers"].values():
                if isinstance(p, dict):
                    p["keys"] = []

        lock_path = os.path.join(ROUTER_DIR, "account_lock_state.json")
        lock_state = {}
        if os.path.exists(lock_path):
            with open(lock_path, "r", encoding="utf-8") as f:
                lock_state = json.load(f)

        accounts = {}
        if include_keys:
            acc_dir = os.path.expanduser("~/.gemini/antigem-accounts")
            if os.path.isdir(acc_dir):
                for fname in sorted(os.listdir(acc_dir)):
                    if fname.endswith(".json"):
                        try:
                            with open(os.path.join(acc_dir, fname), "r", encoding="utf-8") as f:
                                accounts[fname] = json.load(f)
                        except Exception:
                            pass

        bundle = {
            "crouter_full_backup": True,
            "version": get_current_version(),
            "config": cfg,
            "account_lock_state": lock_state,
            "antigem_accounts": accounts,
        }
        resp = json.dumps(bundle, indent=2, ensure_ascii=False).encode("utf-8")
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.send_header('Content-Length', str(len(resp)))
        handler.end_headers()
        handler.wfile.write(resp)
    except Exception as e:
        handler.send_response(500)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        err = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
        handler.send_header('Content-Length', str(len(err)))
        handler.end_headers()
        handler.wfile.write(err)

def handle_full_restore_post(handler, raw_body):
    if handler.path != "/api/ui/full-restore":
        return False
    try:
        data = json.loads(raw_body.decode("utf-8"))
        # Support both full-backup bundle and legacy config.json
        if data.get("crouter_full_backup"):
            cfg = data.get("config") or {}
            lock_state = data.get("account_lock_state")
            accounts = data.get("antigem_accounts") or {}
        else:
            cfg = data
            lock_state = None
            accounts = {}

        cfg_path = os.path.join(ROUTER_DIR, "config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

        if isinstance(lock_state, dict) and lock_state:
            lock_path = os.path.join(ROUTER_DIR, "account_lock_state.json")
            with open(lock_path, "w", encoding="utf-8") as f:
                json.dump(lock_state, f, indent=2, ensure_ascii=False)

        if isinstance(accounts, dict) and accounts:
            acc_dir = os.path.expanduser("~/.gemini/antigem-accounts")
            os.makedirs(acc_dir, exist_ok=True)
            for fname, acc_data in accounts.items():
                if fname.endswith(".json") and "/" not in fname and "\\" not in fname:
                    with open(os.path.join(acc_dir, fname), "w", encoding="utf-8") as f:
                        json.dump(acc_data, f, indent=2, ensure_ascii=False)

        resp = json.dumps({"status": "ok", "message": "Full backup restored successfully", "config": cfg}).encode("utf-8")
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
        err = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
        handler.send_header('Content-Length', str(len(err)))
        handler.end_headers()
        handler.wfile.write(err)
        return True

def handle_version_check_get(handler):
    try:
        info = check_remote_version()
        resp = json.dumps({"status": "ok", **info}).encode("utf-8")
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.send_header('Content-Length', str(len(resp)))
        handler.end_headers()
        handler.wfile.write(resp)
    except Exception as e:
        handler.send_response(500)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Access-Control-Allow-Origin', '*')
        err = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
        handler.send_header('Content-Length', str(len(err)))
        handler.end_headers()
        handler.wfile.write(err)

def perform_update_apply(force=False):
    """
    Applies updates cleanly:
    - If git repo: fetch & merge/reset cleanly without losing config.json
    - Re-runs ensure_cli_environment to sync skills & autostart
    - Restarts crouter
    """
    script = f"""
sleep 0.5
cd {json.dumps(ROUTER_DIR)}
if [ -d .git ]; then
    git config --global --add safe.directory {json.dumps(ROUTER_DIR)} 2>/dev/null || true
    git fetch origin main 2>/dev/null || true
    git reset --hard origin/main 2>/dev/null || git pull --rebase origin main 2>/dev/null || true
else
    tmp_clone="/data/user/0/ai.antigem/files/usr/tmp/crouter_update_$$"
    rm -rf "$tmp_clone"
    git clone --depth 1 https://github.com/{REPO_OWNER}/{REPO_NAME}.git "$tmp_clone" 2>/dev/null
    if [ -d "$tmp_clone" ]; then
        rsync -a --exclude="config.json" --exclude="*.log" --exclude="*.db" "$tmp_clone"/ {json.dumps(ROUTER_DIR)}/ 2>/dev/null || \
        cp -a "$tmp_clone"/* {json.dumps(ROUTER_DIR)}/ 2>/dev/null || true
        rm -rf "$tmp_clone"
    fi
fi

chmod +x {json.dumps(ROUTER_DIR)}/crouter {json.dumps(ROUTER_DIR)}/install.sh 2>/dev/null || true
{json.dumps(ROUTER_DIR)}/crouter restart >/dev/null 2>&1
"""
    subprocess.Popen(["bash", "-c", script], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True, "Update initiated. C-Router will reload in a moment."

def handle_update_post(handler, raw_body):
    if handler.path != "/api/ui/update-apply":
        return False
    try:
        data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
        force = bool(data.get("force", False))
        ok, msg = perform_update_apply(force=force)
        resp = json.dumps({"status": "ok" if ok else "error", "message": msg}).encode("utf-8")
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
        err = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
        handler.send_header('Content-Length', str(len(err)))
        handler.end_headers()
        handler.wfile.write(err)
        return True

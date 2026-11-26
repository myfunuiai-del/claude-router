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

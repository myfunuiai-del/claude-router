#!/usr/bin/env python3
"""
Lightweight Background Transcript Watcher for AntiGem Account-Model Binding.
Watches active transcripts for <USER_SETTINGS_CHANGE> Model Selection
and instantly swaps ~/.gemini/jetski-standalone-oauth-token without touching any proxy or chat flow.
Zero network overhead.
"""
import os
import glob
import time
import re
import sys
import json
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from account_model_lock import load_state, check_and_enforce_binding, get_current_live_email

BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity-cli/brain")
MODEL_REGEX = re.compile(r"The user changed setting `Model Selection` from .*? to (.*?)\.\s*No need to comment")
FORCE_FLAG_FILE = os.path.join(BASE_DIR, ".force_switch")
BUSY_NOTIF_ID = "account_lock_busy"
BUSY_INFO_FILE = os.path.join(BASE_DIR, ".busy_switch_info.json")

MODEL_ID_MAP = {
    "gemini-3-8-flash-low": "Gemini 3.8 Flash (Low)",
    "gemini-3-8-flash-medium": "Gemini 3.8 Flash (Medium)",
    "gemini-3-8-flash-high": "Gemini 3.8 Flash (High)",
    "gemini-4-neon-low": "Gemini 4 Neon (Low)",
    "gemini-4-neon-medium": "Gemini 4 Neon (Medium)",
    "gemini-4-neon-high": "Gemini 4 Neon (High)",
    "gemini-4-hydrogen-low": "Gemini 4 Hydrogen (Low)",
    "gemini-4-hydrogen-medium": "Gemini 4 Hydrogen (Medium)",
    "gemini-4-hydrogen-high": "Gemini 4 Hydrogen (High)",
    "gemini-4-argon-low": "Gemini 4 Argon (Low)",
    "gemini-4-argon-medium": "Gemini 4 Argon (Medium)",
    "gemini-4-argon-high": "Gemini 4 Argon (High)",
    "gpt-oss-120b-low": "GPT-OSS 120B (Low)",
    "gpt-oss-120b-medium": "GPT-OSS 120B (Medium)",
    "gpt-oss-120b-high": "GPT-OSS 120B (High)",
    "claude-sonnet-low": "Claude Sonnet (Low)",
    "claude-sonnet-medium": "Claude Sonnet (Medium)",
    "claude-sonnet-high": "Claude Sonnet (High)",
    "claude-opus-low": "Claude Opus (Low)",
    "claude-opus-medium": "Claude Opus (Medium)",
    "claude-opus-high": "Claude Opus (High)",
}

def is_notification_permission_working():
    """Checks if termux-notification-list succeeds quickly (verifies Termux:API receiver)."""
    try:
        res = subprocess.run(["termux-notification-list"], capture_output=True, text=True, timeout=1.5)
        return res.returncode == 0
    except Exception:
        return False

def show_busy_notification(model_name):
    """Shows heads-up pop-up if permission is active, or triggers dashboard redirect with instructions."""
    try:
        with open(BUSY_INFO_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "busy": True,
                "model": model_name,
                "time": time.time()
            }, f)
    except Exception:
        pass

    if is_notification_permission_working():
        try:
            action_cmd = f"touch '{FORCE_FLAG_FILE}'"
            subprocess.Popen(
                [
                    "termux-notification",
                    "--id", BUSY_NOTIF_ID,
                    "--title", "⏳ Account Switch Waiting",
                    "--content", f"Another chat is busy. Waiting to switch for {model_name}.",
                    "--priority", "max",
                    "--button1", "⚡ Force Switch",
                    "--button1-action", action_cmd,
                    "--action", action_cmd,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    else:
        # Fallback: Notification permission not granted -> redirect user to C-Router dashboard
        try:
            subprocess.Popen(
                ["termux-open-url", "http://127.0.0.1:8999/ui"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

def clear_busy_notification():
    """Dismisses the Busy Lock notification, removes flags, and clears dashboard busy state."""
    try:
        if os.path.exists(FORCE_FLAG_FILE):
            os.remove(FORCE_FLAG_FILE)
    except Exception:
        pass
    try:
        if os.path.exists(BUSY_INFO_FILE):
            os.remove(BUSY_INFO_FILE)
    except Exception:
        pass
    try:
        subprocess.Popen(
            ["termux-notification-remove", BUSY_NOTIF_ID],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

def get_latest_transcripts(limit=8):
    pattern = os.path.join(BRAIN_DIR, "*", ".system_generated", "logs", "transcript.jsonl")
    files = glob.glob(pattern)
    if not files:
        return []
    files.sort(key=os.path.getmtime, reverse=True)
    return files[:limit]

def scan_latest_model_with_source():
    """
    Scans the most recent active transcripts and determines the currently focused chat's model.
    Picks candidate with the newest user activity and model specification.
    """
    files = get_latest_transcripts(8)
    candidates = []
    
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                lines = [l.strip() for l in f if l.strip()]
            if not lines:
                continue

            last_item = json.loads(lines[-1])
            last_activity = last_item.get("created_at") or ""

            # Check if there is an explicit settings change or model field in this chat
            chat_model = None
            for l in reversed(lines):
                if "<USER_SETTINGS_CHANGE>" in l:
                    try:
                        it = json.loads(l)
                        if it.get("source") == "USER_EXPLICIT":
                            m = MODEL_REGEX.search(it.get("content", ""))
                            if m:
                                chat_model = m.group(1).strip().rstrip(".")
                                break
                    except Exception:
                        pass
                try:
                    it = json.loads(l)
                    raw = it.get("model")
                    if raw and raw in MODEL_ID_MAP:
                        chat_model = MODEL_ID_MAP[raw]
                        break
                except Exception:
                    pass

            if chat_model:
                candidates.append((last_activity, os.path.getmtime(fpath), chat_model, fpath))
        except Exception:
            pass

    if not candidates:
        return None, None

    # Sort primarily by newest activity timestamp, then by file modification time
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    top = candidates[0]
    return top[2], top[3]

def scan_latest_model():
    model, _ = scan_latest_model_with_source()
    return model

def is_other_chat_busy(exclude_fpath=None):
    """
    Active-Chat Busy Lock:
    Returns True ONLY if another chat is genuinely in-flight generating or executing tools.
    """
    now = time.time()
    files = get_latest_transcripts(8)
    for fpath in files:
        if exclude_fpath and os.path.abspath(fpath) == os.path.abspath(exclude_fpath):
            continue
        try:
            mtime = os.path.getmtime(fpath)
            # If transcript hasn't been touched in 30s, definitely not actively running
            if (now - mtime) > 30:
                continue

            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                lines = [l.strip() for l in f if l.strip()]
            if not lines:
                continue

            last_item = json.loads(lines[-1])
            src = last_item.get("source")
            typ = last_item.get("type")
            has_tool_calls = bool(last_item.get("tool_calls"))
            has_content = bool(last_item.get("content"))

            # 1. User message waiting for model response
            if src == "USER_EXPLICIT":
                return True

            # 2. Tool result arrived or model planning next step
            if typ in ("GENERIC", "TOOL_RESULT", "SYSTEM_MESSAGE") and (now - mtime) < 20:
                return True

            # 3. Model just issued tool calls -> executing tool
            if has_tool_calls and (now - mtime) < 20:
                return True

            # 4. Final text reply completed (no active tool calls) -> completed turn
            if typ == "PLANNER_RESPONSE" and has_content and not has_tool_calls:
                continue

            # 5. Any intermediate output being written within 10s
            if (now - mtime) < 10:
                return True
        except Exception:
            continue
    return False

def run_listener():
    last_enforced_model = None
    waiting_logged = False

    while True:
        try:
            state = load_state()
            if not state.get("enabled", False):
                if waiting_logged:
                    clear_busy_notification()
                    waiting_logged = False
                time.sleep(2)
                continue

            current_model, src_fpath = scan_latest_model_with_source()
            if current_model and current_model != last_enforced_model:
                force_requested = os.path.exists(FORCE_FLAG_FILE)
                if not force_requested and is_other_chat_busy(exclude_fpath=src_fpath):
                    if not waiting_logged:
                        print(f"[{time.strftime('%X')}] [AccountLock] Busy Lock: waiting for another active chat before switching for {current_model}", flush=True)
                        show_busy_notification(current_model)
                        waiting_logged = True
                    time.sleep(0.5)
                    continue

                if waiting_logged or force_requested:
                    clear_busy_notification()
                    waiting_logged = False

                last_enforced_model = current_model
                success, msg = check_and_enforce_binding(current_model)
                if success:
                    prefix = "[AccountLock] FORCE Enforced" if force_requested else "[AccountLock] Enforced"
                    print(f"[{time.strftime('%X')}] {prefix}: {current_model} -> {msg}", flush=True)

            time.sleep(0.5)
        except Exception as e:
            time.sleep(1)

if __name__ == "__main__":
    run_listener()

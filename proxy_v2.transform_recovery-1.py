#!/usr/bin/env python3
# Modularized per gemini.md Rule 2 (Limit 400-500 lines)
import json
import os
import sys
import re
import copy
import uuid
import time
import base64
import urllib.parse
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
def _is_tool_result_msg(msg):
    """Return True if msg is a user message containing tool_result blocks."""
    if not isinstance(msg, dict) or msg.get("role") != "user":
        return False
    c = msg.get("content")
    if isinstance(c, list):
        return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c)
    return False

def _find_clean_user_index(msgs, target_idx):
    """Find nearest clean user turn (role=user, not an orphaned tool_result) for valid Anthropic slicing."""
    n = len(msgs)
    target_idx = max(0, min(target_idx, n - 1))
    for i in range(target_idx, n):
        if isinstance(msgs[i], dict) and msgs[i].get("role") == "user" and not _is_tool_result_msg(msgs[i]):
            return i
    for i in range(target_idx - 1, -1, -1):
        if isinstance(msgs[i], dict) and msgs[i].get("role") == "user" and not _is_tool_result_msg(msgs[i]):
            return i
    return 0

def _shrink_text(text, max_chars=800):
    if not isinstance(text, str) or len(text) <= max_chars:
        return text
    head = max_chars * 5 // 8
    tail = max_chars - head
    removed = len(text) - head - tail
    return f"{text[:head]}\n...[trimmed {removed} chars by router]...\n{text[-tail:]}"

def _shrink_message_blocks(msg, max_chars=800, tools_only=False):
    """Shrink oversized tool_result (and optionally text/tool_use) payloads inside a single message."""
    changed = False
    if not isinstance(msg, dict):
        return False
    c = msg.get("content")
    if isinstance(c, str):
        if not tools_only:
            new_c = _shrink_text(c, max_chars)
            if new_c != c:
                msg["content"] = new_c
                changed = True
    elif isinstance(c, list):
        for blk in c:
            if not isinstance(blk, dict):
                continue
            btype = blk.get("type")
            if btype == "tool_result":
                tc = blk.get("content")
                if isinstance(tc, str):
                    new_tc = _shrink_text(tc, max_chars)
                    if new_tc != tc:
                        blk["content"] = new_tc
                        changed = True
                elif isinstance(tc, list):
                    for sub in tc:
                        if isinstance(sub, dict) and isinstance(sub.get("text"), str):
                            new_t = _shrink_text(sub["text"], max_chars)
                            if new_t != sub["text"]:
                                sub["text"] = new_t
                                changed = True
            elif not tools_only and btype == "text" and isinstance(blk.get("text"), str):
                new_t = _shrink_text(blk["text"], max_chars)
                if new_t != blk["text"]:
                    blk["text"] = new_t
                    changed = True
            elif btype == "tool_use" and isinstance(blk.get("input"), dict):
                for k, v in list(blk["input"].items()):
                    if isinstance(v, str) and len(v) > max_chars:
                        blk["input"][k] = _shrink_text(v, max_chars)
                        changed = True
    return changed

def is_trimmable_history(body_obj):
    """Return True if body_obj has multi-turn history or oversized content worth trimming on 400/403/413."""
    if not isinstance(body_obj, dict):
        return False
    msgs = body_obj.get("messages")
    if not isinstance(msgs, list) or len(msgs) == 0:
        return False
    if len(msgs) > 1:
        return True
    try:
        return len(json.dumps(msgs, ensure_ascii=False)) > 1500
    except Exception:
        return False

def summarize_omitted_history(omitted_msgs, max_chars=800):
    """Extract concise context from omitted chat history (goal, recent user prompts, turns count)."""
    if not omitted_msgs:
        return ""
    user_texts = []
    for m in omitted_msgs:
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                user_texts.append(c.strip())
            elif isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip():
                        user_texts.append(b["text"].strip())

    parts = []
    if user_texts:
        init_goal = user_texts[0]
        if len(init_goal) > 250:
            init_goal = init_goal[:240] + "..."
        parts.append(f"Goal: {init_goal}")
        if len(user_texts) > 1:
            recent_prompts = user_texts[-3:]
            recent_joined = " -> ".join(p[:120] for p in recent_prompts)
            parts.append(f"Recent instructions: {recent_joined}")
    parts.append(f"({len(omitted_msgs)} earlier turns condensed by router)")
    res = " | ".join(parts)
    if len(res) > max_chars:
        res = res[:max_chars] + "..."
    return res

def make_valid_anthropic_slice(slice_msgs, summary_context=""):
    """Prepare a sliced list of messages guaranteed to be valid for Anthropic API:
    - Must start with role == 'user'
    - If first user message is a tool_result, convert to clean text blocks so Anthropic doesn't reject
    - Embed summary_context so conversational intent is strictly preserved
    """
    if not slice_msgs:
        return []
    res = copy.deepcopy(slice_msgs)
    while res and res[0].get("role") != "user":
        res = res[1:]
    if not res:
        return []

    first = res[0]
    c = first.get("content")
    is_tool_res = isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c)
    if is_tool_res:
        new_blocks = []
        if summary_context:
            new_blocks.append({"type": "text", "text": f"[Earlier Session Context]:\n{summary_context}"})
        for b in c:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                tc = b.get("content", "")
                if isinstance(tc, list):
                    tc = " ".join(sb.get("text", "") for sb in tc if isinstance(sb, dict) and "text" in sb)
                new_blocks.append({"type": "text", "text": f"[Prior Tool Output]:\n{tc}"})
            else:
                new_blocks.append(b)
        first["content"] = new_blocks
    elif summary_context:
        if isinstance(c, str):
            first["content"] = f"[Earlier Session Context]:\n{summary_context}\n\n" + c
        elif isinstance(c, list):
            first["content"] = [{"type": "text", "text": f"[Earlier Session Context]:\n{summary_context}"}] + c

    return res

def build_history_recovery_variants(body_obj, recent_count=8, max_block_chars=800):
    """Build ordered non-mutating recovery variants on 400/403/413 errors:
    1) shrink_old_tools_keep_last: full history + untouched last message, shrinking only older large tool outputs
    2) shrink_all_large_blocks: full history + last message with all large tool outputs and text blocks shrunk
    3) recent_turns_with_context: last ~3-5 turns (6-8 msgs) with embedded session summary context
    4) last_msg_with_context: only the last message with full session context preserved
    5) last_msg_bare: bare last message only (fallback if context block itself is rejected)
    (Stage 6 handled by forwarder: route untouched original full request to next enabled server)
    """
    if not isinstance(body_obj, dict):
        return []
    msgs = body_obj.get("messages")
    if not isinstance(msgs, list) or not msgs:
        return []

    variants = []
    seen_sigs = set()
    try:
        seen_sigs.add(json.dumps(msgs, sort_keys=True, ensure_ascii=False))
    except Exception:
        pass

    def _add_variant(name, new_msgs):
        if not new_msgs:
            return
        try:
            sig = json.dumps(new_msgs, sort_keys=True, ensure_ascii=False)
        except Exception:
            sig = None
        if sig and sig in seen_sigs:
            return
        if sig:
            seen_sigs.add(sig)
        v_obj = copy.deepcopy(body_obj)
        v_obj["messages"] = new_msgs
        variants.append((name, v_obj))

    # Stage 1: Full history + last message untouched; shrink only older large tool outputs
    if len(msgs) > 1:
        old_shrunk = copy.deepcopy(msgs)
        any_old_tool_shrunk = False
        for m in old_shrunk[:-1]:
            if _shrink_message_blocks(m, max_chars=max_block_chars, tools_only=True):
                any_old_tool_shrunk = True
        if any_old_tool_shrunk:
            _add_variant("shrink_old_tools_keep_last", old_shrunk)

    # Stage 2: Full history with ALL large tool outputs & text blocks shrunk
    if len(msgs) > 1:
        all_shrunk = copy.deepcopy(msgs)
        any_all_shrunk = False
        for m in all_shrunk:
            if _shrink_message_blocks(m, max_chars=max_block_chars, tools_only=False):
                any_all_shrunk = True
        if any_all_shrunk:
            _add_variant("shrink_all_large_blocks", all_shrunk)

    # Stage 3: Recent ~3-5 turns (last 6-8 messages) + Full Session Summary Context
    if len(msgs) > 2:
        take_count = min(len(msgs) - 1, max(4, recent_count))
        slice_target = msgs[-take_count:]
        omitted_target = msgs[:-take_count]
        summary_ctx = summarize_omitted_history(omitted_target)
        recent_valid = make_valid_anthropic_slice(slice_target, summary_context=summary_ctx)
        if recent_valid:
            _add_variant(f"recent_with_context_{len(recent_valid)}_msgs", recent_valid)

    # Stage 4: 1 Message Only + FULL CHAT SESSION CONTEXT PRESERVED
    if len(msgs) > 1:
        last_target = [msgs[-1]]
        omitted_all = msgs[:-1]
        full_summary_ctx = summarize_omitted_history(omitted_all, max_chars=1200)
        single_with_ctx = make_valid_anthropic_slice(last_target, summary_context=full_summary_ctx)
        if single_with_ctx:
            _add_variant("last_msg_with_context", single_with_ctx)

    # Stage 5: Bare Last Message Only (only if upstream rejected the context header)
    if len(msgs) > 1:
        single_bare = make_valid_anthropic_slice([msgs[-1]], summary_context="")
        if single_bare:
            _add_variant("last_msg_bare", single_bare)

    return variants

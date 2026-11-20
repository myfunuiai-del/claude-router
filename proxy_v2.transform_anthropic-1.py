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
#!/usr/bin/env python3
import sys
import copy
import json
import re
import uuid

# Regex to find and remove old [Server - Model] tags from chat history
TAG_REGEX = re.compile(r'\n*\s*\[[A-Za-z0-9_\-\.\s/]+ - [A-Za-z0-9_\-\.\s/]+\]\s*$', re.MULTILINE)

def clean_history_tags(body_obj):
    """Strip old footer tags from outgoing messages so model never duplicates them."""
    if not isinstance(body_obj, dict):
        return body_obj
    msgs = body_obj.get('messages', [])
    if isinstance(msgs, list):
        for m in msgs:
            if isinstance(m, dict) and m.get('role') == 'assistant':
                c = m.get('content')
                if isinstance(c, str):
                    m['content'] = TAG_REGEX.sub('', c).strip()
                elif isinstance(c, list):
                    for part in c:
                        if isinstance(part, dict) and part.get('type') == 'text' and 'text' in part:
                            part['text'] = TAG_REGEX.sub('', part['text']).strip()
    return body_obj

_STANDARD_ANTHROPIC_BLOCKS = {
    "text", "image", "document", "tool_use", "tool_result", "thinking", "redacted_thinking"
}

def _sanitize_content_list(blocks):
    """Convert unsupported beta blocks (e.g. tool_reference) into plain text blocks recursively."""
    if not isinstance(blocks, list):
        return blocks
    out = []
    for blk in blocks:
        if not isinstance(blk, dict):
            out.append(blk)
            continue
        btype = blk.get("type")
        if btype == "tool_reference":
            tname = blk.get("tool_name") or blk.get("name") or "tool"
            out.append({"type": "text", "text": f"[tool_reference: {tname}]"})
        elif btype == "tool_result":
            new_blk = dict(blk)
            if isinstance(new_blk.get("content"), list):
                new_blk["content"] = _sanitize_content_list(new_blk["content"])
            out.append(new_blk)
        elif btype == "tool_use":
            new_blk = dict(blk)
            new_blk.pop("caller", None)
            out.append(new_blk)
        elif btype and btype not in _STANDARD_ANTHROPIC_BLOCKS:
            label = blk.get("tool_name") or blk.get("name") or btype
            snippet = blk.get("text") or blk.get("content")
            if isinstance(snippet, str) and snippet.strip():
                txt = f"[{label}]: {snippet[:800]}"
            else:
                txt = f"[{btype}: {label}]"
            out.append({"type": "text", "text": txt})
        else:
            out.append(blk)
    return out

def _enforce_cache_control_limit(body_obj, max_breakpoints=4):
    """Anthropic-compatible APIs reject >4 cache_control breakpoints. Keep the 4 most recent ones."""
    holders = []
    # Collect in priority order (oldest first so we keep the newest 4)
    tools = body_obj.get("tools")
    if isinstance(tools, list):
        for t in tools:
            if isinstance(t, dict) and "cache_control" in t:
                holders.append(t)
    sys_p = body_obj.get("system")
    if isinstance(sys_p, list):
        for s in sys_p:
            if isinstance(s, dict) and "cache_control" in s:
                holders.append(s)
    msgs = body_obj.get("messages")
    if isinstance(msgs, list):
        for m in msgs:
            if not isinstance(m, dict):
                continue
            c = m.get("content")
            if isinstance(c, list):
                for blk in c:
                    if isinstance(blk, dict):
                        if "cache_control" in blk:
                            holders.append(blk)
                        if blk.get("type") == "tool_result" and isinstance(blk.get("content"), list):
                            for sub in blk["content"]:
                                if isinstance(sub, dict) and "cache_control" in sub:
                                    holders.append(sub)
    if len(holders) > max_breakpoints:
        for old_holder in holders[:-max_breakpoints]:
            old_holder.pop("cache_control", None)

def sanitize_anthropic_body(body_obj):
    """Sanitize unsupported beta content blocks (like tool_reference) and cap cache_control at 4."""
    if not isinstance(body_obj, dict):
        return body_obj
    msgs = body_obj.get("messages")
    if isinstance(msgs, list):
        for m in msgs:
            if isinstance(m, dict) and isinstance(m.get("content"), list):
                m["content"] = _sanitize_content_list(m["content"])
    _enforce_cache_control_limit(body_obj, max_breakpoints=4)
    return body_obj

def is_signature_enabled():
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f).get("show_model_signature", True) is not False
    except Exception:
        pass
    return True

def append_signature_to_response(resp_data, server, model):
    """Append [Server - Model] signature to standard JSON or SSE stream response."""
    if not is_signature_enabled():
        return resp_data
    sig = f"\n\n[{server} - {model}]"
    try:
        text = resp_data.decode('utf-8', errors='ignore')

        # 1. Handle SSE Event-Stream format
        if "data:" in text:
            sep = "\r\n\r\n" if "\r\n\r\n" in text else "\n\n"
            nl = "\r\n" if sep == "\r\n\r\n" else "\n"
            raw_events = text.split(sep)

            if f"[{server} - {model}]" in text:
                return resp_data

            parsed = []
            for i, blk in enumerate(raw_events):
                data_lines = [
                    ln[5:].lstrip()
                    for ln in blk.splitlines()
                    if ln.startswith("data:")
                ]
                payload_str = "\n".join(data_lines).strip()
                obj = None
                if payload_str and payload_str != "[DONE]":
                    try:
                        obj = json.loads(payload_str)
                    except Exception:
                        obj = None
                parsed.append((i, blk, payload_str, obj))

            # Anthropic SSE
            if any(isinstance(o, dict) and o.get("type", "").startswith(("message_", "content_block_")) for _, _, _, o in parsed):
                # Ensure message_start has valid id and model
                for orig_i, blk, payload_str, obj in parsed:
                    if isinstance(obj, dict) and obj.get("type") == "message_start":
                        msg = obj.get("message")
                        if isinstance(msg, dict):
                            modified = False
                            if not msg.get("id"):
                                msg["id"] = f"msg_{uuid.uuid4().hex[:24]}"
                                modified = True
                            if not msg.get("model"):
                                msg["model"] = model
                                modified = True
                            if "stop_reason" not in msg:
                                msg["stop_reason"] = None
                                modified = True
                            if modified:
                                raw_events[orig_i] = f"event: message_start{nl}data: {json.dumps(obj)}"

                # Check if stop_reason is tool_use
                for _, _, _, o in parsed:
                    if isinstance(o, dict) and o.get("type") == "message_delta":
                        if o.get("delta", {}).get("stop_reason") == "tool_use":
                            return sep.join(raw_events).encode('utf-8')

                text_idx = None
                for _, _, _, o in parsed:
                    if not isinstance(o, dict):
                        continue
                    if o.get("type") == "content_block_start" and o.get("content_block", {}).get("type") == "text":
                        text_idx = o.get("index")
                    elif o.get("type") == "content_block_delta" and o.get("delta", {}).get("type") == "text_delta":
                        text_idx = o.get("index")

                # If no text block exists (e.g. only thinking block), append a text block
                if text_idx is None:
                    max_idx = -1
                    for _, _, _, o in parsed:
                        if isinstance(o, dict) and "index" in o:
                            max_idx = max(max_idx, o["index"])
                    new_idx = max_idx + 1
                    extra_events = [
                        f"event: content_block_start{nl}data: {json.dumps({'type':'content_block_start','index':new_idx,'content_block':{'type':'text','text':''}})}",
                        f"event: content_block_delta{nl}data: {json.dumps({'type':'content_block_delta','index':new_idx,'delta':{'type':'text_delta','text':sig.strip()}})}",
                        f"event: content_block_stop{nl}data: {json.dumps({'type':'content_block_stop','index':new_idx})}",
                        f"event: message_delta{nl}data: {json.dumps({'type':'message_delta','delta':{'stop_reason':'end_turn'}})}",
                        f"event: message_stop{nl}data: {json.dumps({'type':'message_stop'})}"
                    ]
                    cleaned_events = [ev for ev in raw_events if ev.strip() and not ev.startswith("event: message_stop") and not ev.startswith("event: message_delta")]
                    cleaned_events.extend(extra_events)
                    return (sep.join(cleaned_events) + sep).encode('utf-8')

                stop_pos = None
                for i, _, _, o in parsed:
                    if isinstance(o, dict) and o.get("type") == "content_block_stop" and o.get("index") == text_idx:
                        stop_pos = i

                delta_payload = json.dumps({
                    "type": "content_block_delta",
                    "index": text_idx,
                    "delta": {"type": "text_delta", "text": sig}
                }, ensure_ascii=False)

                if stop_pos is not None:
                    inj_blk = f"event: content_block_delta{nl}data: {delta_payload}"
                    raw_events.insert(stop_pos, inj_blk)
                    return sep.join(raw_events).encode('utf-8')
                else:
                    extra_events = [
                        f"event: content_block_delta{nl}data: {delta_payload}",
                        f"event: content_block_stop{nl}data: {json.dumps({'type':'content_block_stop','index':text_idx})}",
                        f"event: message_delta{nl}data: {json.dumps({'type':'message_delta','delta':{'stop_reason':'end_turn'}})}",
                        f"event: message_stop{nl}data: {json.dumps({'type':'message_stop'})}"
                    ]
                    cleaned_events = [ev for ev in raw_events if ev.strip()]
                    cleaned_events.extend(extra_events)
                    return (sep.join(cleaned_events) + sep).encode('utf-8')

        # 2. Non-streaming Standard JSON
        obj = json.loads(text)
        if 'content' in obj and isinstance(obj['content'], list):
            if obj.get('stop_reason') == 'tool_use':
                return resp_data
            has_text = False
            for part in reversed(obj['content']):
                if part.get('type') == 'text' and 'text' in part:
                    if f"[{server} - {model}]" not in part['text']:
                        part['text'] = part['text'] + sig
                    has_text = True
                    break
            if not has_text:
                obj['content'].append({"type": "text", "text": sig.strip()})
            return json.dumps(obj, ensure_ascii=False).encode('utf-8')
        elif 'choices' in obj and isinstance(obj['choices'], list):
            for ch in obj['choices']:
                if 'message' in ch and 'content' in ch['message'] and ch['message']['content']:
                    if f"[{server} - {model}]" not in ch['message']['content']:
                        ch['message']['content'] = ch['message']['content'] + sig
                    break
            return json.dumps(obj, ensure_ascii=False).encode('utf-8')

    except Exception:
        pass
    return resp_data

_NORMAL_MODE_ALLOWED_TOKENS = (
    "ask_question", "askuserquestion", "ask_user", "user_question", "prompt_user",
    "write_file", "edit_file", "read_file", "image", "invoke_subagent"
)

def _is_normal_mode_allowed_tool(name):
    """Return True if tool is allowed in Normal mode (file ops, question, image, subagent). Excludes heavy/dangerous tools."""
    n = (name or "").lower().replace("-", "_")
    if any(bad in n for bad in ("bash", "run_command", "terminal", "browser", "delete", "rm", "unlink", "workflow", "schedule", "manage_task", "send_message")):
        return False
    return any(tok in n for tok in _NORMAL_MODE_ALLOWED_TOKENS)

def _is_interactive_question_tool(name):
    return _is_normal_mode_allowed_tool(name)

def slim_system_prompt_for_normal_mode(sys_p):
    """Strip heavy agent bloat while preserving Identity, User Rules, Subagents (image-generator), and adding Image capability."""
    if isinstance(sys_p, list):
        out = []
        for blk in sys_p:
            if isinstance(blk, dict) and blk.get("type") == "text" and isinstance(blk.get("text"), str):
                nb = dict(blk)
                nb["text"] = slim_system_prompt_for_normal_mode(blk["text"])
                out.append(nb)
            else:
                out.append(blk)
        return out
    elif isinstance(sys_p, str):
        cleaned = sys_p
        # Keep subagents intact so the model knows about image-generator without external URL calls
        tags_to_strip = (
            "mcp_servers", "skills", "conversation_transcript",
            "slash_commands", "messaging", "artifacts", "guidelines", "communication_style"
        )
        for tag in tags_to_strip:
            cleaned = re.sub(rf"<{tag}>.*?</{tag}>", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        img_directive = (
            "\n\n[Image Generation Directive: When asked to generate, create, or draw an image, "
            "call the invoke_subagent tool with TypeName='image-generator', Role='Image Generator', "
            "and a descriptive prompt. Do NOT use external URLs or web links. Render the returned local file path in chat.]"
        )
        if "[Image Generation Directive" not in cleaned:
            cleaned += img_directive
        return cleaned
    return sys_p

def _extract_tool_result_text(content, is_error=False):
    """Flatten Anthropic tool_result content (string or block list) into clean text."""
    if isinstance(content, str):
        txt = content
    elif isinstance(content, list):
        parts = []
        for sub in content:
            if isinstance(sub, dict):
                st = sub.get("type")
                if st == "text" and isinstance(sub.get("text"), str):
                    parts.append(sub["text"])
                elif st == "tool_reference":
                    parts.append(f"[tool_reference: {sub.get('tool_name') or sub.get('name') or 'tool'}]")
                elif st == "image":
                    parts.append("[image]")
            elif isinstance(sub, str):
                parts.append(sub)
        txt = "\n".join(parts)
    else:
        txt = ""
    if is_error and txt:
        return f"[Error]: {txt}"
    return txt or "(empty)"

def apply_engine_mode_to_anthropic_body(body_obj, mode="agentic"):
    """Apply server engine mode ('agentic' vs 'normal') to an Anthropic Messages payload.
    - agentic: full tools, tool_choice, thinking, and multi-turn tool calls untouched.
    - normal: strip heavy coding/exec tools (saving ~10k+ tokens/turn) while KEEPING interactive
      question tools (e.g. ask_question / AskUserQuestion) so the model can still ask options.
      Historical tool_use/tool_result blocks for stripped tools are converted cleanly to text.
    """
    if not isinstance(body_obj, dict) or (mode or "agentic").lower() != "normal":
        return dict(body_obj) if isinstance(body_obj, dict) else body_obj

    b = copy.deepcopy(body_obj)
    raw_tools = b.get("tools")
    kept_tools = []
    kept_names = set()
    if isinstance(raw_tools, list):
        for t in raw_tools:
            if isinstance(t, dict) and _is_interactive_question_tool(t.get("name")):
                kept_tools.append(t)
                kept_names.add(t.get("name"))

    if kept_tools:
        b["tools"] = kept_tools
        tc = b.get("tool_choice")
        if isinstance(tc, dict) and tc.get("type") == "tool" and tc.get("name") not in kept_names:
            b["tool_choice"] = {"type": "auto"}
    else:
        b.pop("tools", None)
        b.pop("tool_choice", None)

    # Convert historical tool_use/tool_result for stripped tools into clean text so upstream won't 400
    kept_call_ids = set()
    msgs = b.get("messages")
    if isinstance(msgs, list):
        for m in msgs:
            if not isinstance(m, dict) or not isinstance(m.get("content"), list):
                continue
            new_content = []
            for blk in m["content"]:
                if not isinstance(blk, dict):
                    new_content.append(blk)
                    continue
                btype = blk.get("type")
                if btype == "tool_use":
                    tname = blk.get("name", "tool")
                    tid = blk.get("id", "")
                    if tname in kept_names:
                        if tid:
                            kept_call_ids.add(tid)
                        new_content.append(blk)
                    else:
                        try:
                            tinp = json.dumps(blk.get("input", {}), ensure_ascii=False)[:400]
                        except Exception:
                            tinp = ""
                        new_content.append({"type": "text", "text": f"[Earlier Tool Call: {tname}({tinp})]"})
                elif btype == "tool_result":
                    tid = blk.get("tool_use_id", "")
                    if tid and tid in kept_call_ids:
                        new_content.append(blk)
                    else:
                        res_txt = _extract_tool_result_text(blk.get("content", ""), blk.get("is_error", False))[:1200]
                        new_content.append({"type": "text", "text": f"[Earlier Tool Result]: {res_txt}"})
                else:
                    new_content.append(blk)
            m["content"] = new_content

    if b.get("system"):
        b["system"] = slim_system_prompt_for_normal_mode(b["system"])

    return b


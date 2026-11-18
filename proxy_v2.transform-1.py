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

def append_signature_to_response(resp_data, server, model):
    """Append [Server - Model] signature to standard JSON or SSE stream response."""
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

_INTERACTIVE_Q_TOKENS = ("ask_question", "askuserquestion", "ask_user", "user_question", "prompt_user")

def _is_interactive_question_tool(name):
    """Return True if tool name is an interactive user-question tool (kept even in Normal mode)."""
    n = (name or "").lower().replace("-", "_")
    return any(tok in n for tok in _INTERACTIVE_Q_TOKENS)

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

    return b

_OPENAI_ALLOWED_FORMATS = {"enum", "date-time"}
_OPENAI_STRIP_SCHEMA_KEYS = {
    "$schema", "$id", "$defs", "definitions", "additionalProperties",
    "propertyNames", "examples", "exclusiveMinimum", "exclusiveMaximum",
    "const", "patternProperties", "$comment", "minProperties", "maxProperties",
    "minLength", "maxLength", "pattern", "uniqueItems", "minItems", "maxItems"
}

def _sanitize_openai_schema(schema):
    """Recursively sanitize JSON Schema for strict OpenAI-compatible endpoints (especially Google Gemini)."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    out = {}
    # Handle anyOf / oneOf simplification (e.g. nullable types)
    for union_key in ("anyOf", "oneOf"):
        if union_key in schema and isinstance(schema[union_key], list):
            non_null = [s for s in schema[union_key] if isinstance(s, dict) and s.get("type") != "null"]
            if non_null:
                merged = dict(non_null[0])
                if "description" in schema and "description" not in merged:
                    merged["description"] = schema["description"]
                return _sanitize_openai_schema(merged)

    for k, v in schema.items():
        if k in _OPENAI_STRIP_SCHEMA_KEYS:
            continue
        if k == "format":
            if isinstance(v, str) and v in _OPENAI_ALLOWED_FORMATS:
                out[k] = v
            continue
        if k == "type":
            if isinstance(v, list):
                non_null = [t for t in v if t != "null"]
                out["type"] = non_null[0] if non_null else "string"
            else:
                out["type"] = v
        elif k == "properties" and isinstance(v, dict):
            out["properties"] = {pk: _sanitize_openai_schema(pv) for pk, pv in v.items() if isinstance(pv, dict)}
        elif k == "items":
            if isinstance(v, dict):
                out["items"] = _sanitize_openai_schema(v)
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                out["items"] = _sanitize_openai_schema(v[0])
            else:
                out["items"] = {"type": "string"}
        elif k == "required" and isinstance(v, list):
            out["required"] = list(v)
        elif k == "enum" and isinstance(v, list):
            # Gemini OpenAI-compat requires enum values to be strings
            out["enum"] = [str(item) for item in v]
        else:
            out[k] = v

    if "type" not in out:
        if "properties" in out:
            out["type"] = "object"
        elif "items" in out:
            out["type"] = "array"
        else:
            out["type"] = "string"

    if out.get("type") == "object":
        if "properties" not in out or not isinstance(out["properties"], dict):
            out["properties"] = {}
        if "required" in out:
            valid_req = [r for r in out["required"] if r in out["properties"]]
            if valid_req:
                out["required"] = valid_req
            else:
                out.pop("required", None)
    elif out.get("type") == "array":
        if "items" not in out:
            out["items"] = {"type": "string"}

    return out

# Process-wide cache for Gemini 3.x OpenAI-compat thought_signature per tool_call_id
if "_claude_router_thought_sigs" not in sys.modules:
    sys.modules["_claude_router_thought_sigs"] = {}
_THOUGHT_SIG_CACHE = sys.modules["_claude_router_thought_sigs"]

def _store_thought_sig(tc_id, extra_content):
    if not tc_id or not isinstance(extra_content, dict):
        return
    sig = (extra_content.get("google") or {}).get("thought_signature")
    if isinstance(sig, str) and sig:
        if len(_THOUGHT_SIG_CACHE) > 500:
            # Drop oldest ~100 entries to keep memory bounded
            for old_k in list(_THOUGHT_SIG_CACHE.keys())[:100]:
                _THOUGHT_SIG_CACHE.pop(old_k, None)
        _THOUGHT_SIG_CACHE[tc_id] = sig

def anthropic_to_openai_body(body_obj, default_model="openai/gpt-oss-120b", p_id="", mode="agentic", base_url=""):
    """Modern bidirectional Anthropic Messages -> OpenAI Chat Completions converter.
    Supports:
    - Agentic Mode (default): Full tools, tool_choice, multi-turn tool_calls/tool_result pairing,
      Gemini 3.x thought_signature round-trip preservation, vision images, and full context window.
    - Normal Mode: Lightweight fast chat while preserving interactive ask_question tools.
    - Groq-specific compaction guard only when targeting Groq free tier.
    """
    eff_mode = (mode or "agentic").lower()
    is_groq = (p_id or "").lower() == "groq"
    is_gemini_oai = (
        "generativelanguage.googleapis.com" in (base_url or "").lower()
        or (p_id or "").lower() in ("googlestudio", "google", "gemini")
        or "gemini" in (default_model or "").lower()
    )

    # 1. Convert Tools according to mode
    raw_tools = body_obj.get("tools") or []
    openai_tools = []
    active_tool_names = set()
    if isinstance(raw_tools, list):
        for t in raw_tools:
            if not isinstance(t, dict):
                continue
            tname = t.get("name")
            if not tname:
                continue
            if eff_mode == "normal" and not _is_interactive_question_tool(tname):
                continue
            params = _sanitize_openai_schema(t.get("input_schema") or {"type": "object", "properties": {}})
            desc = t.get("description") or f"Tool {tname}"
            if is_groq and len(desc) > 400:
                desc = desc[:400] + "..."
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tname,
                    "description": desc,
                    "parameters": params
                }
            })
            active_tool_names.add(tname)

    # 2. System prompt
    messages = []
    sys_prompt = body_obj.get("system")
    if sys_prompt:
        if isinstance(sys_prompt, list):
            sys_prompt = "\n".join([p.get("text", "") for p in sys_prompt if isinstance(p, dict) and p.get("type") == "text"])
        if isinstance(sys_prompt, str) and sys_prompt.strip():
            if is_groq and eff_mode == "normal" and len(sys_prompt) > 2500:
                sys_prompt = sys_prompt[:2500] + "\n[System instructions trimmed for Groq context budget]"
            messages.append({"role": "system", "content": sys_prompt})

    # 3. Convert multi-turn messages with strict tool_call_id pairing
    raw_msgs = body_obj.get("messages", [])
    conv_msgs = []
    valid_call_ids = set()
    id_map = {}

    def _normalize_tool_call_id(raw_id):
        if not raw_id:
            return f"call_{uuid.uuid4().hex[:16]}"
        if raw_id in id_map:
            return id_map[raw_id]
        # Strict alphanumeric with call_ prefix for strict OpenAI providers
        cleaned = re.sub(r'[^a-zA-Z0-9_]', '', raw_id)
        if not cleaned.startswith("call_"):
            cleaned = f"call_{cleaned}"
        id_map[raw_id] = cleaned
        return cleaned

    for m in raw_msgs:
        if not isinstance(m, dict):
            continue
        role = m.get("role", "user")
        c = m.get("content", "")

        if role == "assistant":
            text_parts = []
            assistant_tool_calls = []
            if isinstance(c, str):
                if c.strip():
                    text_parts.append(c.strip())
            elif isinstance(c, list):
                for p in c:
                    if not isinstance(p, dict):
                        continue
                    ptype = p.get("type")
                    if ptype == "text" and isinstance(p.get("text"), str) and p["text"].strip():
                        text_parts.append(p["text"])
                    elif ptype == "tool_use":
                        tname = p.get("name", "tool")
                        raw_tid = p.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                        tid = _normalize_tool_call_id(raw_tid)
                        tinp_obj = p.get("input", {})
                        try:
                            tinp_json = json.dumps(tinp_obj, ensure_ascii=False)
                        except Exception:
                            tinp_json = "{}"
                        if tname in active_tool_names:
                            tc_obj = {
                                "id": tid,
                                "type": "function",
                                "function": {
                                    "name": tname,
                                    "arguments": tinp_json
                                }
                            }
                            if is_gemini_oai:
                                sig = _THOUGHT_SIG_CACHE.get(raw_tid) or _THOUGHT_SIG_CACHE.get(tid) or "skip_thought_signature_validator"
                                tc_obj["extra_content"] = {"google": {"thought_signature": sig}}
                            assistant_tool_calls.append(tc_obj)
                            valid_call_ids.add(raw_tid)
                            valid_call_ids.add(tid)
                        else:
                            text_parts.append(f"[Tool Call: {tname}({tinp_json[:400]})]")
            msg_out = {"role": "assistant"}
            joined_txt = "\n".join(text_parts).strip()
            if assistant_tool_calls:
                msg_out["content"] = joined_txt if joined_txt else None
                msg_out["tool_calls"] = assistant_tool_calls
                conv_msgs.append(msg_out)
            elif joined_txt:
                msg_out["content"] = joined_txt
                conv_msgs.append(msg_out)

        else:
            # role == "user" (may contain tool_result, text, image blocks)
            tool_result_msgs = []
            user_text_parts = []
            user_content_blocks = []
            has_image = False

            if isinstance(c, str):
                if c.strip():
                    user_text_parts.append(c.strip())
            elif isinstance(c, list):
                for p in c:
                    if not isinstance(p, dict):
                        continue
                    ptype = p.get("type")
                    if ptype == "tool_result":
                        raw_tid = p.get("tool_use_id") or ""
                        norm_tid = _normalize_tool_call_id(raw_tid)
                        res_txt = _extract_tool_result_text(p.get("content", ""), p.get("is_error", False))
                        if is_groq and len(res_txt) > 3000:
                            res_txt = res_txt[:3000] + "\n...[trimmed for Groq]"
                        if raw_tid and (raw_tid in valid_call_ids or norm_tid in valid_call_ids):
                            tool_result_msgs.append({
                                "role": "tool",
                                "tool_call_id": norm_tid,
                                "content": res_txt
                            })
                        else:
                            user_text_parts.append(f"[Tool Result]: {res_txt[:2000]}")
                    elif ptype == "text" and isinstance(p.get("text"), str) and p["text"].strip():
                        user_text_parts.append(p["text"])
                        user_content_blocks.append({"type": "text", "text": p["text"]})
                    elif ptype == "image" and isinstance(p.get("source"), dict):
                        src = p["source"]
                        if src.get("type") == "base64" and src.get("data"):
                            mtype = src.get("media_type", "image/jpeg")
                            has_image = True
                            user_content_blocks.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{mtype};base64,{src['data']}"}
                            })
                    elif ptype == "tool_reference":
                        ref_txt = f"[tool_reference: {p.get('tool_name') or p.get('name') or 'tool'}]"
                        user_text_parts.append(ref_txt)
                        user_content_blocks.append({"type": "text", "text": ref_txt})

            # Emit paired role="tool" messages first (immediately following assistant tool_calls)
            conv_msgs.extend(tool_result_msgs)

            if has_image and user_content_blocks:
                conv_msgs.append({"role": "user", "content": user_content_blocks})
            else:
                joined_u = "\n".join(x for x in user_text_parts if x).strip()
                if joined_u:
                    conv_msgs.append({"role": "user", "content": joined_u})

    if not conv_msgs:
        conv_msgs = [{"role": "user", "content": "Continue"}]

    # Apply Groq-specific free-tier budget guard only for Groq normal mode
    if is_groq and eff_mode == "normal":
        if len(conv_msgs) > 4:
            conv_msgs = conv_msgs[-4:]
            while conv_msgs and conv_msgs[0].get("role") == "tool":
                conv_msgs = conv_msgs[1:]
        for m in conv_msgs:
            if isinstance(m.get("content"), str) and len(m["content"]) > 3000:
                m["content"] = m["content"][:3000] + "\n[Message content trimmed for Groq limit]"

    messages.extend(conv_msgs)

    model = default_model if (default_model and default_model != "unknown") else body_obj.get("model", default_model)
    if isinstance(model, str) and model.startswith("@") and "/" in model:
        model = model.split("/", 1)[1]
    if not model or model == "unknown":
        model = default_model

    req_max_tokens = body_obj.get("max_tokens")
    if isinstance(req_max_tokens, int) and req_max_tokens > 0:
        max_tokens = min(req_max_tokens, 4096 if is_groq else 8192)
    else:
        max_tokens = 2048 if is_groq else 4096

    stream = body_obj.get("stream", False)

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream
    }
    if "temperature" in body_obj and body_obj["temperature"] is not None:
        payload["temperature"] = body_obj["temperature"]

    if openai_tools:
        payload["tools"] = openai_tools
        tc = body_obj.get("tool_choice")
        if isinstance(tc, dict):
            tc_type = tc.get("type")
            if tc_type == "auto":
                payload["tool_choice"] = "auto"
            elif tc_type == "any":
                payload["tool_choice"] = "required"
            elif tc_type == "none":
                payload["tool_choice"] = "none"
            elif tc_type == "tool" and tc.get("name") in active_tool_names:
                payload["tool_choice"] = {"type": "function", "function": {"name": tc["name"]}}

    return payload

def _parse_tool_args_safely(args_str):
    """Parse OpenAI function arguments string into dict + valid JSON string."""
    s = (args_str or "").strip()
    if not s:
        return {}, "{}"
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed, json.dumps(parsed, ensure_ascii=False)
        return {"value": parsed}, json.dumps({"value": parsed}, ensure_ascii=False)
    except Exception:
        return {"raw": s}, json.dumps({"raw": s}, ensure_ascii=False)

def convert_openai_stream_to_anthropic(openai_stream_text, server, model):
    """Convert OpenAI SSE stream into full Anthropic SSE stream with thinking, text, and tool_use blocks."""
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    anthropic_events = []

    lines = openai_stream_text.splitlines()
    text_content = ""
    reasoning_content = ""
    tool_calls_map = {}  # index -> {"id": str, "name": str, "arguments": str}
    finish_reason = None
    input_tokens = 10
    output_tokens = 0

    for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data_str = line[5:].strip()
        if not data_str or data_str == "[DONE]":
            continue
        try:
            chunk = json.loads(data_str)
        except Exception:
            continue

        usage = chunk.get("usage")
        if isinstance(usage, dict):
            if usage.get("prompt_tokens"):
                input_tokens = usage["prompt_tokens"]
            if usage.get("completion_tokens"):
                output_tokens = usage["completion_tokens"]

        choices = chunk.get("choices", [])
        if not choices:
            continue
        c0 = choices[0]
        if c0.get("finish_reason"):
            finish_reason = c0["finish_reason"]

        delta = c0.get("delta") or {}
        if not isinstance(delta, dict):
            continue

        r_piece = delta.get("reasoning_content") or delta.get("reasoning")
        if isinstance(r_piece, str) and r_piece:
            reasoning_content += r_piece

        c_piece = delta.get("content")
        if isinstance(c_piece, str) and c_piece:
            text_content += c_piece

        tc_deltas = delta.get("tool_calls")
        if isinstance(tc_deltas, list):
            for tcd in tc_deltas:
                if not isinstance(tcd, dict):
                    continue
                tc_idx = tcd.get("index", 0)
                if tc_idx not in tool_calls_map:
                    tool_calls_map[tc_idx] = {
                        "id": tcd.get("id") or f"toolu_{uuid.uuid4().hex[:18]}",
                        "name": "",
                        "arguments": ""
                    }
                elif tcd.get("id"):
                    tool_calls_map[tc_idx]["id"] = tcd["id"]
                if tcd.get("extra_content"):
                    _store_thought_sig(tool_calls_map[tc_idx]["id"], tcd["extra_content"])
                fn = tcd.get("function") or {}
                if isinstance(fn, dict):
                    if fn.get("name"):
                        tool_calls_map[tc_idx]["name"] += fn["name"]
                    if fn.get("arguments"):
                        tool_calls_map[tc_idx]["arguments"] += fn["arguments"]

    assembled_tools = [tool_calls_map[k] for k in sorted(tool_calls_map.keys()) if tool_calls_map[k].get("name")]

    # 1. message_start
    msg_start = {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": 0}
        }
    }
    anthropic_events.append(f"event: message_start\ndata: {json.dumps(msg_start, ensure_ascii=False)}")

    blk_idx = 0

    # 2. Thinking block (if model produced reasoning_content / reasoning)
    if reasoning_content.strip():
        anthropic_events.append(f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': blk_idx, 'content_block': {'type': 'thinking', 'thinking': ''}}, ensure_ascii=False)}")
        anthropic_events.append(f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': blk_idx, 'delta': {'type': 'thinking_delta', 'thinking': reasoning_content}}, ensure_ascii=False)}")
        anthropic_events.append(f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': blk_idx}, ensure_ascii=False)}")
        blk_idx += 1

    # 3. Text block (emit if text present, OR if no tool calls were produced)
    has_text = bool(text_content.strip())
    if has_text or not assembled_tools:
        final_text = text_content if has_text else (reasoning_content.strip() if reasoning_content.strip() else "...")
        # Append [Server - Model] signature on final text turns (avoid cluttering pure tool-call turns)
        if not assembled_tools:
            final_text += f"\n\n[{server} - {model}]"
        anthropic_events.append(f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': blk_idx, 'content_block': {'type': 'text', 'text': ''}}, ensure_ascii=False)}")
        anthropic_events.append(f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': blk_idx, 'delta': {'type': 'text_delta', 'text': final_text}}, ensure_ascii=False)}")
        anthropic_events.append(f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': blk_idx}, ensure_ascii=False)}")
        blk_idx += 1

    # 4. Tool Use blocks (triggers native Claude Code tool execution!)
    for tc in assembled_tools:
        _, valid_json_str = _parse_tool_args_safely(tc.get("arguments", ""))
        tc_start = {
            "type": "content_block_start",
            "index": blk_idx,
            "content_block": {
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": {}
            }
        }
        tc_delta = {
            "type": "content_block_delta",
            "index": blk_idx,
            "delta": {
                "type": "input_json_delta",
                "partial_json": valid_json_str
            }
        }
        tc_stop = {"type": "content_block_stop", "index": blk_idx}
        anthropic_events.append(f"event: content_block_start\ndata: {json.dumps(tc_start, ensure_ascii=False)}")
        anthropic_events.append(f"event: content_block_delta\ndata: {json.dumps(tc_delta, ensure_ascii=False)}")
        anthropic_events.append(f"event: content_block_stop\ndata: {json.dumps(tc_stop, ensure_ascii=False)}")
        blk_idx += 1

    # 5. message_delta with exact Anthropic stop_reason
    if assembled_tools or finish_reason in ("tool_calls", "function_call"):
        stop_reason = "tool_use"
    elif finish_reason == "length":
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"

    if not output_tokens:
        est_len = len(text_content) + len(reasoning_content) + sum(len(tc.get("arguments", "")) for tc in assembled_tools)
        output_tokens = max(est_len // 4, 1)

    msg_delta = {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": output_tokens}
    }
    anthropic_events.append(f"event: message_delta\ndata: {json.dumps(msg_delta, ensure_ascii=False)}")

    # 6. message_stop
    anthropic_events.append(f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}")

    return ("\n\n".join(anthropic_events) + "\n\n").encode('utf-8')

def convert_openai_json_to_anthropic(openai_obj, server, model):
    """Convert OpenAI Chat Completion JSON into Anthropic Message JSON with thinking, text & tool_use."""
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    choices = openai_obj.get("choices", [])
    content_blocks = []
    finish_reason = None
    tool_calls = []
    content_text = ""
    reasoning_text = ""

    if choices:
        c0 = choices[0]
        finish_reason = c0.get("finish_reason")
        msg = c0.get("message", {}) or {}
        content_text = msg.get("content") or ""
        reasoning_text = msg.get("reasoning_content") or msg.get("reasoning") or ""
        tool_calls = msg.get("tool_calls") or []

    if reasoning_text.strip():
        content_blocks.append({"type": "thinking", "thinking": reasoning_text})

    valid_tools = []
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            tname = fn.get("name")
            if not tname:
                continue
            tid = tc.get("id") or f"toolu_{uuid.uuid4().hex[:18]}"
            if tc.get("extra_content"):
                _store_thought_sig(tid, tc["extra_content"])
            parsed_inp, _ = _parse_tool_args_safely(fn.get("arguments", ""))
            valid_tools.append({
                "type": "tool_use",
                "id": tid,
                "name": tname,
                "input": parsed_inp
            })

    if content_text.strip() or not valid_tools:
        final_text = content_text if content_text.strip() else (reasoning_text.strip() if reasoning_text.strip() else "...")
        if not valid_tools:
            final_text += f"\n\n[{server} - {model}]"
        content_blocks.append({"type": "text", "text": final_text})

    content_blocks.extend(valid_tools)

    if valid_tools or finish_reason in ("tool_calls", "function_call"):
        stop_reason = "tool_use"
    elif finish_reason == "length":
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"

    usage = openai_obj.get("usage", {}) or {}
    return json.dumps({
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 10),
            "output_tokens": usage.get("completion_tokens", max(1, len(content_text) // 4))
        }
    }, ensure_ascii=False).encode('utf-8')

def extract_anthropic_usage(resp_bytes):
    """Extract (input_tokens, output_tokens) from Anthropic JSON or SSE response bytes."""
    in_tok = 0
    out_tok = 0
    if not resp_bytes:
        return 0, 0
    try:
        text = resp_bytes.decode('utf-8', errors='ignore')
        stripped = text.lstrip()
        if stripped.startswith("{"):
            obj = json.loads(stripped)
            u = obj.get("usage")
            if isinstance(u, dict):
                in_tok = int(u.get("input_tokens") or u.get("prompt_tokens") or 0)
                out_tok = int(u.get("output_tokens") or u.get("completion_tokens") or 0)
            return in_tok, out_tok
        # SSE scan
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]" or not payload.startswith("{"):
                continue
            try:
                ev = json.loads(payload)
            except Exception:
                continue
            # message_start -> message.usage
            msg_u = (ev.get("message") or {}).get("usage")
            if isinstance(msg_u, dict):
                if msg_u.get("input_tokens"):
                    in_tok = max(in_tok, int(msg_u["input_tokens"]))
                if msg_u.get("output_tokens"):
                    out_tok = max(out_tok, int(msg_u["output_tokens"]))
            # message_delta -> usage
            ev_u = ev.get("usage")
            if isinstance(ev_u, dict):
                if ev_u.get("input_tokens"):
                    in_tok = max(in_tok, int(ev_u["input_tokens"]))
                if ev_u.get("output_tokens"):
                    out_tok = max(out_tok, int(ev_u["output_tokens"]))
    except Exception:
        pass
    return in_tok, out_tok

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

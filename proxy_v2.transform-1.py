#!/usr/bin/env python3
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

def anthropic_to_openai_body(body_obj, default_model="openai/gpt-oss-120b"):
    """Convert incoming Anthropic Messages body into standard OpenAI Chat Completion body for Groq, with Smart Prompt Trimmer for Groq's 7,000 ITPM limit."""
    messages = []
    sys_prompt = body_obj.get("system")
    if sys_prompt:
        if isinstance(sys_prompt, list):
            sys_prompt = "\n".join([p.get("text", "") for p in sys_prompt if isinstance(p, dict) and p.get("type") == "text"])
        if isinstance(sys_prompt, str):
            # Smart Prompt Trimmer: Groq free tier limit is 7,000 ITPM. Keep system prompt compact.
            if len(sys_prompt) > 1500:
                sys_prompt = sys_prompt[:1500] + "\n[System instructions trimmed for Groq context budget]"
            messages.append({"role": "system", "content": sys_prompt})

    raw_msgs = body_obj.get("messages", [])
    conv_msgs = []
    for m in raw_msgs:
        role = m.get("role", "user")
        c = m.get("content", "")
        if isinstance(c, str):
            txt = c.strip()
        elif isinstance(c, list):
            parts = []
            for p in c:
                if not isinstance(p, dict):
                    continue
                ptype = p.get("type")
                if ptype == "text" and isinstance(p.get("text"), str):
                    parts.append(p["text"])
                elif ptype == "tool_use":
                    tname = p.get("name", "tool")
                    try:
                        tinp = json.dumps(p.get("input", {}), ensure_ascii=False)[:400]
                    except Exception:
                        tinp = ""
                    parts.append(f"[Tool Call: {tname}({tinp})]")
                elif ptype == "tool_result":
                    tc = p.get("content", "")
                    if isinstance(tc, str):
                        t_txt = tc[:1200]
                    elif isinstance(tc, list):
                        sub_parts = []
                        for sub in tc:
                            if isinstance(sub, dict):
                                if sub.get("type") == "text" and isinstance(sub.get("text"), str):
                                    sub_parts.append(sub["text"])
                                elif sub.get("type") == "tool_reference":
                                    sub_parts.append(f"[tool_reference: {sub.get('tool_name') or sub.get('name') or 'tool'}]")
                        t_txt = "\n".join(sub_parts)[:1200]
                    else:
                        t_txt = ""
                    if t_txt:
                        parts.append(f"[Tool Result: {t_txt}]")
                elif ptype == "tool_reference":
                    parts.append(f"[tool_reference: {p.get('tool_name') or p.get('name') or 'tool'}]")
            txt = "\n".join(x for x in parts if x).strip()
        else:
            txt = ""
        if txt:
            conv_msgs.append({"role": role, "content": txt})
    if not conv_msgs:
        conv_msgs = [{"role": "user", "content": "Continue"}]

    # Groq free tier has a strict 7,000 ITPM (~18,000 chars) limit. Keep last 2-4 messages and under 6,000 chars.
    if len(conv_msgs) > 2:
        conv_msgs = conv_msgs[-2:]
    total_chars = sum(len(m["content"]) for m in conv_msgs)
    if total_chars > 6000:
        for m in conv_msgs:
            if len(m["content"]) > 3000:
                m["content"] = m["content"][:3000] + "\n[Message content trimmed for Groq limit]"

    messages.extend(conv_msgs)

    model = default_model if (default_model and default_model != "unknown") else body_obj.get("model", default_model)
    if isinstance(model, str) and model.startswith("@") and "/" in model:
        model = model.split("/", 1)[1]
    if not model or model == "unknown":
        model = default_model

    max_tokens = min(body_obj.get("max_tokens", 2048), 2048)
    stream = body_obj.get("stream", False)

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream
    }
    if "temperature" in body_obj:
        payload["temperature"] = body_obj["temperature"]
    return payload

def convert_openai_stream_to_anthropic(openai_stream_text, server, model):
    """Convert Groq OpenAI SSE stream into Anthropic SSE stream."""
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    anthropic_events = []

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
            "usage": {"input_tokens": 10, "output_tokens": 0}
        }
    }
    anthropic_events.append(f"event: message_start\ndata: {json.dumps(msg_start)}")

    # 2. content_block_start
    blk_start = {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""}
    }
    anthropic_events.append(f"event: content_block_start\ndata: {json.dumps(blk_start)}")

    lines = openai_stream_text.splitlines()
    text_content = ""
    for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data_str = line[5:].strip()
        if not data_str or data_str == "[DONE]":
            continue
        try:
            chunk = json.loads(data_str)
            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            content_piece = delta.get("content")
            if content_piece:
                text_content += content_piece
                delta_ev = {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": content_piece}
                }
                anthropic_events.append(f"event: content_block_delta\ndata: {json.dumps(delta_ev)}")
        except Exception:
            continue

    if not text_content.strip():
        # Fallback to reasoning tokens if content was empty
        reasoning_text = ""
        for line in lines:
            line = line.strip()
            if line.startswith("data:") and "[DONE]" not in line:
                try:
                    c = json.loads(line[5:].strip())
                    r = c.get("choices", [{}])[0].get("delta", {}).get("reasoning", "")
                    if r:
                        reasoning_text += r
                except Exception:
                    pass
        text_content = reasoning_text.strip() if reasoning_text.strip() else "Hello!"
        delta_ev = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": text_content}
        }
        anthropic_events.append(f"event: content_block_delta\ndata: {json.dumps(delta_ev)}")

    # Append signature
    sig = f"\n\n[{server} - {model}]"
    sig_ev = {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": sig}
    }
    anthropic_events.append(f"event: content_block_delta\ndata: {json.dumps(sig_ev)}")

    # 3. content_block_stop
    blk_stop = {"type": "content_block_stop", "index": 0}
    anthropic_events.append(f"event: content_block_stop\ndata: {json.dumps(blk_stop)}")

    # 4. message_delta
    msg_delta = {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": max(len(text_content) // 4, 1)}
    }
    anthropic_events.append(f"event: message_delta\ndata: {json.dumps(msg_delta)}")

    # 5. message_stop
    msg_stop = {"type": "message_stop"}
    anthropic_events.append(f"event: message_stop\ndata: {json.dumps(msg_stop)}")

    return ("\n\n".join(anthropic_events) + "\n\n").encode('utf-8')

def convert_openai_json_to_anthropic(openai_obj, server, model):
    """Convert Groq OpenAI JSON into Anthropic Message JSON."""
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    choices = openai_obj.get("choices", [])
    content_text = ""
    if choices:
        msg = choices[0].get("message", {})
        content_text = msg.get("content") or msg.get("reasoning") or ""
    if not content_text:
        content_text = "Hello!"
    sig = f"\n\n[{server} - {model}]"
    usage = openai_obj.get("usage", {})
    return json.dumps({
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [
            {
                "type": "text",
                "text": content_text + sig
            }
        ],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 10),
            "output_tokens": usage.get("completion_tokens", max(1, len(content_text) // 4))
        }
    }, ensure_ascii=False).encode('utf-8')

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

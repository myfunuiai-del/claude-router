#!/usr/bin/env python3
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
            conv_msgs.append({"role": role, "content": c})
        elif isinstance(c, list):
            txt = "".join([p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"])
            conv_msgs.append({"role": role, "content": txt})

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

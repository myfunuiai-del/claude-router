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
_anthropic_mod = _load_module_to_globals("proxy_v2.transform_anthropic-1.py", globals())
_openai_mod = _load_module_to_globals("proxy_v2.transform_openai-1.py", globals())
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
    cached_input_tokens = 0
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
            elif usage.get("input_tokens"):
                input_tokens = usage["input_tokens"]
            if usage.get("completion_tokens"):
                output_tokens = usage["completion_tokens"]
            elif usage.get("output_tokens"):
                output_tokens = usage["output_tokens"]

        # Support Responses API streaming SSE
        ctype = chunk.get("type")
        if ctype == "response.output_text.delta":
            d = chunk.get("delta")
            if isinstance(d, str):
                text_content += d
            continue
        elif ctype == "response.reasoning_text.delta":
            d = chunk.get("delta")
            if isinstance(d, str):
                reasoning_content += d
            continue
        elif ctype == "response.output_item.added":
            item = chunk.get("item") or {}
            if item.get("type") == "function_call":
                out_idx = chunk.get("output_index", 0)
                fc_id = item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:16]}"
                tool_calls_map[out_idx] = {
                    "id": fc_id,
                    "name": item.get("name") or "",
                    "arguments": item.get("arguments") or ""
                }
            continue
        elif ctype == "response.function_call_arguments.delta":
            out_idx = chunk.get("output_index", 0)
            delta_arg = chunk.get("delta")
            if isinstance(delta_arg, str) and delta_arg:
                if out_idx not in tool_calls_map:
                    tool_calls_map[out_idx] = {
                        "id": chunk.get("call_id") or chunk.get("item_id") or f"call_{uuid.uuid4().hex[:16]}",
                        "name": "",
                        "arguments": ""
                    }
                tool_calls_map[out_idx]["arguments"] += delta_arg
            continue
        elif ctype == "response.function_call_arguments.done":
            out_idx = chunk.get("output_index", 0)
            full_args = chunk.get("arguments")
            if isinstance(full_args, str) and full_args:
                if out_idx in tool_calls_map:
                    tool_calls_map[out_idx]["arguments"] = full_args
                else:
                    tool_calls_map[out_idx] = {
                        "id": chunk.get("call_id") or chunk.get("item_id") or f"call_{uuid.uuid4().hex[:16]}",
                        "name": "",
                        "arguments": full_args
                    }
            continue
        elif ctype == "response.output_item.done":
            item = chunk.get("item") or {}
            if item.get("type") == "function_call":
                out_idx = chunk.get("output_index", 0)
                fc_id = item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:16]}"
                if out_idx not in tool_calls_map:
                    tool_calls_map[out_idx] = {"id": fc_id, "name": item.get("name") or "", "arguments": ""}
                if item.get("name"):
                    tool_calls_map[out_idx]["name"] = item["name"]
                if item.get("arguments"):
                    tool_calls_map[out_idx]["arguments"] = item["arguments"]
            continue
        elif ctype in ("response.done", "response.completed"):
            resp_info = chunk.get("response") or {}
            usg = resp_info.get("usage")
            if isinstance(usg, dict):
                raw_in = usg.get("input_tokens") or usg.get("prompt_tokens") or input_tokens
                raw_cached = (usg.get("input_tokens_details") or {}).get("cached_tokens") or (usg.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
                if raw_cached > 0:
                    cached_input_tokens = raw_cached
                    input_tokens = max(raw_in - raw_cached, 1)
                else:
                    input_tokens = raw_in
                output_tokens = usg.get("output_tokens") or usg.get("completion_tokens") or output_tokens
            continue

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
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": cached_input_tokens
            }
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
            sig_on = is_signature_enabled() if "is_signature_enabled" in globals() else True
            if sig_on:
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
        "usage": {
            "output_tokens": output_tokens,
            "input_tokens": input_tokens,
            "cache_read_input_tokens": cached_input_tokens
        }
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
    elif "output" in openai_obj:
        for item in openai_obj.get("output", []):
            if isinstance(item, dict):
                itype = item.get("type")
                if itype == "message":
                    for cblk in item.get("content", []):
                        if isinstance(cblk, dict) and cblk.get("type") in ("output_text", "text"):
                            content_text += cblk.get("text", "")
                elif itype == "reasoning":
                    for s in item.get("summary", []):
                        if isinstance(s, dict) and s.get("text"):
                            reasoning_text += s.get("text") + "\n"
                elif itype == "function_call":
                    tool_calls.append({
                        "id": item.get("call_id") or item.get("id"),
                        "type": "function",
                        "function": {
                            "name": item.get("name"),
                            "arguments": item.get("arguments") or ""
                        }
                    })

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
            sig_on = is_signature_enabled() if "is_signature_enabled" in globals() else True
            if sig_on:
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
    raw_in = usage.get("prompt_tokens") or usage.get("input_tokens") or 10
    raw_cached = (usage.get("input_tokens_details") or {}).get("cached_tokens") or (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
    actual_in = max(raw_in - raw_cached, 1) if raw_cached > 0 else raw_in
    return json.dumps({
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": actual_in,
            "cache_read_input_tokens": raw_cached,
            "cache_creation_input_tokens": 0,
            "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens") or max(1, len(content_text) // 4)
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


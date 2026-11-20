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
            if eff_mode == "normal":
                check_fn = globals().get("_is_normal_mode_allowed_tool") or globals().get("_is_interactive_question_tool")
                if check_fn and not check_fn(tname):
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
    else:
        sys_prompt = ""

    if eff_mode == "normal":
        if "slim_system_prompt_for_normal_mode" in globals():
            sys_prompt = slim_system_prompt_for_normal_mode(sys_prompt)
        elif hasattr(_anthropic_mod, "slim_system_prompt_for_normal_mode"):
            sys_prompt = _anthropic_mod.slim_system_prompt_for_normal_mode(sys_prompt)
        if is_groq and len(sys_prompt) > 2500:
            sys_prompt = sys_prompt[:2500] + "\n[System instructions trimmed for Groq context budget]"

    if isinstance(sys_prompt, str) and sys_prompt.strip():
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


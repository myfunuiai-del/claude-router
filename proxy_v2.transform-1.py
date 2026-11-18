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

# Submodules orchestrated per gemini.md Rule 2:
_anthropic_mod = _load_module_to_globals("proxy_v2.transform_anthropic-1.py", globals())
_openai_mod = _load_module_to_globals("proxy_v2.transform_openai-1.py", globals())
_stream_mod = _load_module_to_globals("proxy_v2.transform_stream-1.py", globals())
_recovery_mod = _load_module_to_globals("proxy_v2.transform_recovery-1.py", globals())

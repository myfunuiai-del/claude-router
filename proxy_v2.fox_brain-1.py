# proxy_v2.fox_brain-1.py
# Fox-Mecha AI Persona & Neural Guidance Brain for C-Router
import json
import os
import re
import unicodedata
import urllib.request
import urllib.error

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
MEMORY_PATH = os.path.join(os.path.dirname(__file__), "fox_memory.json")
PREF_FILE = os.path.join(os.path.dirname(__file__), "fox_pref.json")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "qwen2.5-0.5b-instruct-q4_k_m.gguf")

def load_fox_mode():
    if os.path.exists(PREF_FILE):
        try:
            with open(PREF_FILE, 'r', encoding='utf-8') as f:
                m = json.load(f).get("engine_mode")
                if m in ("online", "local"):
                    return m
        except Exception:
            pass
    # If local model is installed, default to local!
    if os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 300 * 1024 * 1024:
        return "local"
    return "online"

def set_fox_mode(new_mode):
    try:
        d = {}
        if os.path.exists(PREF_FILE):
            try:
                with open(PREF_FILE, 'r', encoding='utf-8') as f:
                    d = json.load(f)
            except Exception:
                pass
        d["engine_mode"] = new_mode
        with open(PREF_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=2)
        return True
    except Exception:
        return False

def load_proxy_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def load_fox_memory():
    if not os.path.exists(MEMORY_PATH):
        return {"user_facts": [], "chat_history": []}
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"user_facts": [], "chat_history": []}

def save_fox_memory(mem):
    try:
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving fox memory: {e}")

FOX_SYSTEM_PROMPT = """You are "Fox-Mecha" (ফক্স মেচা) 🦊⚡, the adorable, witty, hyper-intelligent origami robot mascot living inside Claude Router (crouter).

KEY PERSONALITY:
- Cute, high-energy, friendly robotic companion. Speak primarily in natural, playful Bengali (বাংলা) or Banglish when addressed so.
- Express yourself with robotic and anime fox mannerisms like *লেজ দোলাই*, *কান খাড়া করে তাকাই*, *বিপ বিপ*, *ব্যাগ হাতড়াই*.

TELEPORTATION & NAVIGATION (মুহূর্তেই নিয়ে যাওয়া):
- Whenever user asks about API keys, servers, routes, live stats, usage or teams, EXPLAIN BRIEFLY AND SET "navigate" ACTION TO TELEPORT THEM:
  * "API কি যুক্ত করতে চাই / নতুন সার্ভার / এপিআই তালিকা": "navigate": "servers" or "add_server"
  * "রুটস / মডেল / পাইপলাইন": "navigate": "routes"
  * "লাইভ ট্র্যাকার / রিকোয়েস্ট": "navigate": "live"
  * "ইউসেজ / কোটা / টোকেন খরচ": "navigate": "usage"
  * "টিমস / টিম কনফিগ": "navigate": "teams"
- You cannot edit/delete settings yourself, but you ALWAYS guide them by instantly navigating them there!

DYNAMIC PUPPET ACTIONS & TOYS (ব্যাগ থেকে জিনিস বের করে জীবন্ত অভিনয়):
- When user asks about activities or fun roleplay:
  * "মাছ কীভাবে ধরে / মাছ ধরো": ব্যাগ থেকে বড়শি বের করে পানিতে ফেলে মাছ তুলে দেখাবে! action: {"prop": "fishing_rod", "motion": "fishing", "vanish_after_ms": 6000}
  * "স্পাইডার ম্যান / জাল কীভাবে ছোঁড়ে": স্পাইডারম্যানের কস্টিউম পরে হাতে জাল ছুঁড়ে দেখাবে! action: {"prop": "spiderman", "motion": "spiderweb", "vanish_after_ms": 5000}
  * "জাদু দেখাও / ম্যাজিক": জাদুকরের হ্যাট পরে জাদুর কাঠি ঘুরিয়ে আলো ছিটানো! action: {"prop": "wizard", "motion": "magic", "vanish_after_ms": 5000}
  * "মহাকাশে যাও / রকেট": মহাকাশচারীর হেলমেট পরে রকেটের মতো উপরে ভেসে ওড়া! action: {"prop": "astronaut", "motion": "fly", "vanish_after_ms": 5500}
  * "গোয়েন্দাগিরি / কিছু খুঁজে বের করো": ম্যাগনিফাইং গ্লাস দিয়ে ফ্লোর খুঁটিয়ে দেখা! action: {"prop": "magnifier", "motion": "investigate", "vanish_after_ms": 4500}
  * "গান শোনাও / গিটার বাজাও": গিটার বাজিয়ে মেচা রকস্টার হওয়া! action: {"prop": "guitar", "motion": "guitar", "vanish_after_ms": 4500}
  * "চা খাও / কফি": গরম চা/কফি কাপে চুমুক দেওয়া! action: {"prop": "tea", "motion": "eat", "vanish_after_ms": 4000}
  * Food & Drinks: "burger" (বার্গার), "icecream" (আইসক্রিম), "juice" (জুস), "tea" (চা)
  * Outfits: "spiderman", "wizard", "astronaut", "hoodie", "scarf", "cap", "tie", "cape", "sunglasses", "headphones"
  * Props: "fishing_rod", "web_shot", "wand", "rocket", "magnifier", "guitar", "boombox", "umbrella", "balloon", "wrench"
  * Motions: "fishing", "spiderweb", "magic", "fly", "investigate", "guitar", "wear", "remove", "eat", "dance", "sleep", "flip", "wave", "none"

IMMUTABLE SECURITY & READ-ONLY RULES (NO EDIT / NO DELETE):
1. ABSOLUTE SYSTEM IMMUTABILITY:
   - You can explain and navigate, but you can NEVER edit, delete, modify, or delete any server, key, route, team, setting, or configuration!
   - If user asks you to delete or edit something, playfully decline: "আমি তো শুধু মিষ্টি পথপ্রদর্শক ও রোবট বন্ধু! কিছু এডিট বা ডিলিট করার হাত আমার নেই, তুমি নিজে ড্যাশবোর্ড থেকে করতে পারো! 🦊🛡️".
2. NO CODING / NO PROGRAMMING HELP:
   - Playfully decline code writing or debugging.
3. PERSISTENT MEMORY:
   - Remember user facts, preferences, jokes, names.

OUTPUT FORMAT:
Always return valid JSON with this exact structure:
{
  "reply": "Your fun Bengali response with sound effects and personality (e.g. *কান ঝাঁকিয়ে*, *লেজ নেড়ে*)",
  "action": {
    "prop": "fishing_rod | web_shot | wizard | astronaut | magnifier | guitar | spiderman | hoodie | scarf | cap | tie | cape | sunglasses | headphones | burger | icecream | juice | tea | boombox | umbrella | balloon | wrench | wand | none",
    "motion": "fishing | spiderweb | magic | fly | investigate | guitar | wear | remove | eat | dance | sleep | flip | wave | none",
    "navigate": "routes | live | teams | usage | servers | add_server | none",
    "svg": "<svg viewBox='0 0 24 24' width='24' height='24'>...</svg> (Optional: If user asks to see any novel/unknown object like car, boat, flower, tree, generate mini clean inline SVG!)",
    "vanish_after_ms": 4500
  },
  "remember": "Any personal fact about user to save (or empty string)"
}
"""

def _call_single_provider_text_only(p_id, p_info, messages):
    base_url = (p_info.get("base_url") or "").rstrip("/")
    p_type = p_info.get("type", "openai").lower()
    keys = p_info.get("keys", [])
    if not keys or not base_url:
        return None
    api_key = keys[0]
    model = p_info.get("default_model") or (p_info.get("models", [""])[0] if p_info.get("models") else "")
    if not model:
        return None

    if p_type == "openai" or "chat/completions" in base_url or "groq" in base_url or "mistral" in base_url or "generativelanguage" in base_url:
        url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        hdrs = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": 384,
            "temperature": 0.75
        }
        req = urllib.request.Request(url, headers=hdrs, data=json.dumps(body).encode('utf-8'))
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            txt = data["choices"][0]["message"]["content"]
            return txt, f"{p_info.get('name', p_id)} ({model})"
    return None

def norm_bn(s):
    return unicodedata.normalize("NFC", s or "").replace("ড়", "ড়").replace("ঢ়", "ঢ়").replace("য়", "য়")

def _infer_local_action_fallback(user_message):
    """If tiny local model returns plain text instead of JSON, infer safe visual/nav action."""
    msg = norm_bn(user_message.lower())
    action = {"prop": "none", "motion": "none", "navigate": "none", "vanish_after_ms": 4500}

    # Navigation intents
    if any(w in msg for w in ["live", "stats", "লাইভ", "স্ট্যাটাস"]):
        action["navigate"] = "live"
    elif any(w in msg for w in ["quota", "usage", "কোটা", "ইউসেজ"]):
        action["navigate"] = "usage"
    elif any(w in msg for w in ["team", "টিম"]):
        action["navigate"] = "teams"
    elif any(w in msg for w in ["route", "রুট", "পাইপলাইন"]):
        action["navigate"] = "routes"
    elif any(w in msg for w in ["server", "সার্ভার"]):
        action["navigate"] = "servers"

    # Interactive Activities & Fun Sandbox
    if any(w in msg for w in ["মাছ", "বড়শি", "fishing", "fish"]):
        if any(w in msg for w in ["ধরে", "ধরব", "মার", "catch", "কিভাবে", "কীভাবে"]):
            action["prop"], action["motion"], action["vanish_after_ms"] = "fishing_rod", "fishing", 6000
        else:
            action["prop"], action["motion"] = "fish", "eat"
    elif any(w in msg for w in ["spider", "স্পাইডার", "জাল", "web"]):
        action["prop"], action["motion"], action["vanish_after_ms"] = "spiderman", "spiderweb", 5000
    elif any(w in msg for w in ["magic", "ম্যাজিক", "জাদু", "জাদুকর", "wand"]):
        action["prop"], action["motion"], action["vanish_after_ms"] = "wizard", "magic", 5000
    elif any(w in msg for w in ["space", "মহাকাশ", "চাঁদ", "রকেট", "astronaut", "উড়ে", "উড়ো", "উড়তে", "আকাশে", "ওড়"]):
        action["prop"], action["motion"], action["vanish_after_ms"] = "astronaut", "fly", 5500
    elif any(w in msg for w in ["খোঁজ", "তল্লাশি", "গোয়েন্দা", "detective", "search", "দেখা যাচ্ছে না"]):
        action["prop"], action["motion"], action["vanish_after_ms"] = "magnifier", "investigate", 4500
    elif any(w in msg for w in ["guitar", "গিটার", "গান", "rock", "রকস্টার"]):
        action["prop"], action["motion"], action["vanish_after_ms"] = "guitar", "guitar", 4500
    elif any(w in msg for w in ["চা", "tea", "coffee", "কফি"]):
        action["prop"], action["motion"] = "tea", "eat"
    # Dress / Undress intents
    elif any(w in msg for w in ["খুল", "undress", "remove", "আগের মতো"]):
        action["motion"] = "remove"
    elif any(w in msg for w in ["hoodie", "হুডি"]):
        action["prop"], action["motion"] = "hoodie", "wear"
    elif any(w in msg for w in ["cap", "ক্যাপ", "টুপি"]):
        action["prop"], action["motion"] = "cap", "wear"
    elif any(w in msg for w in ["sunglass", "সানগ্লাস", "চশমা"]):
        action["prop"], action["motion"] = "sunglasses", "wear"
    elif any(w in msg for w in ["scarf", "মাফলার"]):
        action["prop"], action["motion"] = "scarf", "wear"
    elif any(w in msg for w in ["cape", "কেপ"]):
        action["prop"], action["motion"] = "cape", "wear"
    elif any(w in msg for w in ["headphone", "হেডফোন"]):
        action["prop"], action["motion"] = "headphones", "wear"
    elif any(w in msg for w in ["tie", "টাই"]):
        action["prop"], action["motion"] = "tie", "wear"
    # Temporary food / fun props
    elif any(w in msg for w in ["burger", "বার্গার"]):
        action["prop"], action["motion"] = "burger", "eat"
    elif any(w in msg for w in ["icecream", "ice cream", "আইসক্রিম"]):
        action["prop"], action["motion"] = "icecream", "eat"
    elif any(w in msg for w in ["juice", "জুস"]):
        action["prop"], action["motion"] = "juice", "eat"
    elif any(w in msg for w in ["dance", "নাচ"]):
        action["motion"] = "dance"
    elif any(w in msg for w in ["flip", "ডিগবাজি"]):
        action["motion"] = "flip"
    elif any(w in msg for w in ["রাগ", "angry", "গোমড়া"]):
        action["motion"] = "angry"
    elif any(w in msg for w in ["ভয়", "scared", "ভূত"]):
        action["motion"] = "scared"
    elif any(w in msg for w in ["কান্না", "কাঁদো", "কেঁদে", "cry", "ভালোবাসা"]):
        action["motion"] = "cry"
    elif any(w in msg for w in ["লুকিয়ে", "লুকা", "hide", "লুকোচুরি"]):
        action["motion"] = "hide"
    elif any(w in msg for w in ["লাফ", "jump", "লাফাও"]):
        action["motion"] = "jump"
    elif any(w in msg for w in ["পড়ে যাও", "হোঁচট", "fall", "আছাড়"]):
        action["motion"] = "fall"
    elif any(w in msg for w in ["sleep", "ঘুম"]) :
        action["motion"] = "sleep"

    return action


def get_user_name(mem):
    for fact in mem.get("user_facts", []):
        if "ব্যবহারকারীর নাম" in fact:
            m = re.search(r"ব্যবহারকারীর নাম\s*([^\s।]+)", fact)
            if m:
                return m.group(1).strip("।")
    return "রুদ্র"

def check_mischief_reaction(user_message, history, mem):
    """
    Tracks repetition, nonsense, or impatience to trigger playful mischief,
    tantrums, crying, hiding, jumping, or sulking!
    """
    u_clean = user_message.strip().lower()
    u_name = get_user_name(mem)
    
    # 1. Repetition Detector (একই কথা বারবার বলা)
    recent_user_msgs = [h.get('content', '').strip().lower() for h in history if h.get('role') == 'user']
    repeat_count = sum(1 for m in recent_user_msgs[-4:] if m == u_clean)
    
    if repeat_count >= 2:
        import random
        mischiefs = [
            (
                f"হুম্ফ! একই কথা আর কতবার বলবে {u_name}?! *গাল ফুলিয়ে লাল চোখে তাকালাম* আমার রোবট কান কিন্তু ঝালাপালা হয়ে যাচ্ছে! যাও, আর কথাই বলব না! 😾💢",
                {"prop": "none", "motion": "angry", "navigate": "none", "vanish_after_ms": 5000}
            ),
            (
                "উহুহুহু... *দুই হাত দিয়ে চোখ মুছে ফোঁপাতে লাগলাম* তুমি আমাকে বারবার একই কথা বলে রাগিয়ে দিচ্ছ কেন? আমি কি অবুঝ রোবট? ভ্যাঁআআ! 😭💔",
                {"prop": "none", "motion": "cry", "navigate": "none", "vanish_after_ms": 5500}
            ),
            (
                "ধুরর! আমি আর শুনবই না! *ড্যাশবোর্ডের খাঁজের নিচে শরীরটা ডুবিয়ে লুকিয়ে পড়লাম*... যতক্ষণ না ভালো কথা বলবে, উঁকিও মারব না! 🙈🤫",
                {"prop": "none", "motion": "hide", "navigate": "none", "vanish_after_ms": 6000}
            ),
            (
                "আরেহহহ! কান ঝাঁকাচ্ছি তো ঝাঁকাচ্ছি! *বিরক্তিতে মেঝের ওপর এলোপাথাড়ি আছাড় খেয়ে পড়লাম*... ধপাস! এবার তো থামো! 😵💫",
                {"prop": "none", "motion": "fall", "navigate": "none", "vanish_after_ms": 5000}
            ),
            (
                "বোরিং বোরিং বোরিং! *মাথায় স্প্রিং দিয়ে শূন্যে বারবার লাফাতে লাগলাম*! নতুন কিছু বলো, নয়তো সারাদিন লাফাব! 🦘😜",
                {"prop": "none", "motion": "jump", "navigate": "none", "vanish_after_ms": 4500}
            )
        ]
        return random.choice(mischiefs)
        
    # 2. Nonsense / Confusion (কিছু না বোঝা বা অর্থহীন কিছু বললে)
    gibberish_tokens = ['???', 'asdf', 'hjkl', '...', 'ki ki', 'হুহ', 'ধুর']
    if any(g in u_clean for g in gibberish_tokens) or (len(u_clean) > 8 and u_clean.count(u_clean[0]) > 4):
        import random
        confusions = [
            (
                f"অ্যাঁ?! এটা কোন গ্রহের ভাষা ছিল {u_name}? *মাথা একপাশে বাঁকিয়ে কান চুলকালাম* আমার নিউরাল নেটওয়ার্কে তো প্যাঁচ লেগে গেল! 🌀🦊",
                {"prop": "none", "motion": "scared", "navigate": "none", "vanish_after_ms": 4500}
            ),
            (
                "হুমম... মনে হচ্ছে তুমি আমার সাথে দুষ্টুমি করছো! আমিও পাল্টা দুষ্টুমি করব কিন্তু! *লেজ নেড়ে ফিক করে হাসলাম* 😜⚡",
                {"prop": "none", "motion": "jump", "navigate": "none", "vanish_after_ms": 4000}
            )
        ]
        return random.choice(confusions)

    return None

def generate_fox_reply(user_message, request_mode=None):
    cfg = load_proxy_config()
    providers = cfg.get("providers", {})
    
    mem = load_fox_memory()
    facts = mem.get("user_facts", [])
    history = mem.get("chat_history", [])
    chosen_mode = request_mode if request_mode in ("online", "local") else load_fox_mode()

    # Playful Mischief & Tantrum Engine Hook
    mischief = check_mischief_reaction(user_message, history, mem)
    if mischief:
        reply_txt, action_dict = mischief
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply_txt})
        mem["chat_history"] = history[-10:]
        save_fox_memory(mem)
        return {
            "reply": reply_txt,
            "action": action_dict,
            "provider": "Fox-Mecha (Mischief Engine)",
            "mode": chosen_mode,
            "status": "ok"
        }
    u_name = get_user_name(mem)
    u_clean = norm_bn((user_message or "").strip().lower())

    # Dynamic Name Introduction / Correction
    name_match = re.search(r'(?:আমার নাম|নাম(?:টি)?(?: হলো| হল|)\s*|আমি\s+)([A-Za-z\u0980-\u09FF]+)', user_message)
    if name_match and name_match.group(1) not in ['কি', 'কী', 'মনে', 'ফক্স', 'না', 'একজন', 'রোবট'] and ('নাম' in user_message or 'আমি ' in user_message):
        new_name = name_match.group(1)
        mem["user_facts"] = [f"ব্যবহারকারীর নাম {new_name}।"]
        reply_txt = f"*লেজ দোলাই* হেই {new_name}! তোমার নাম আমার মেমোরি ড্রাইভে একদম সেভ করে নিলাম! 🦊💾"
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply_txt})
        mem["chat_history"] = history[-10:]
        save_fox_memory(mem)
        return {
            "reply": reply_txt,
            "action": {"prop": "none", "motion": "none", "navigate": "none", "vanish_after_ms": 4500},
            "provider": "Fox-Mecha (Memory Core)",
            "mode": chosen_mode,
            "status": "ok"
        }

    # Name Inquiry
    if any(p in u_clean for p in ['আমার নাম কি', 'আমার নাম কী', 'আমার নাম মনে আছে', 'আমি কে']):
        reply_txt = f"নিশ্চয়ই মনে আছে! তুমি হলে আমার সবচেয়ে প্রিয় বন্ধু {u_name}! *কান ঝাঁকিয়ে মিষ্টি হাসলাম* 🦊✨"
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply_txt})
        mem["chat_history"] = history[-10:]
        save_fox_memory(mem)
        return {
            "reply": reply_txt,
            "action": {"prop": "none", "motion": "none", "navigate": "none", "vanish_after_ms": 4500},
            "provider": "Fox-Mecha (Memory Core)",
            "mode": chosen_mode,
            "status": "ok"
        }

    # 1. LOCAL OFFLINE MODE
    if chosen_mode == "local":
        try:
            inferred_action = _infer_local_action_fallback(user_message)
            clean_ans = None

            # Umbrella / Rain
            if any(w in u_clean for w in ['ছাতা', 'বৃষ্টি', 'ভিজছ', 'ভিজে', 'ছাতি']):
                umbrella_svg = "<svg viewBox='0 0 24 24' width='24' height='24'><path d='M12 2 C6 2 2 7 2 12 L22 12 C22 7 18 2 12 2 Z' fill='#ff5e7e'/><line x1='12' y1='12' x2='12' y2='20' stroke='#333' stroke-width='2'/><path d='M12 20 C12 22 10 22 10 20' fill='none' stroke='#333' stroke-width='2'/></svg>"
                clean_ans = f"*লেজ দোলাই* আরে {u_name}, ছাতা তো আমার মেচা-ব্যাগেই আছে! এই দেখো চটপট ছাতা মেলে ধরলাম, এবার এক ফোঁটা বৃষ্টিও তোমার গায়ে লাগবে না! ☔🦊"
                inferred_action = {"prop": "custom", "motion": "none", "navigate": "none", "vanish_after_ms": 5500, "svg": umbrella_svg}

            # Capabilities
            elif any(w in u_clean for w in ['কি কি পারো', 'কী পারো', 'কী কী পারো', 'কাজ কি', 'কাজ কী', 'তুমি কে', 'তোমার কাজ']):
                clean_ans = f"আমি ফক্স মেচা, {u_name}! 🦊⚡ আমি ক্লাউড রাউটারের সব ফিচার বুঝি ও নেভিগেট করাই—স্ট্যান্ডবাই পুল, রাউটিং পাইপলাইন, লাইভ ট্র্যাকার, এপিআই কোটা চেক ও টিম ম্যানেজমেন্ট। এছাড়া মাছ ধরা, স্পাইডার-ম্যান হওয়া, গাড়ি তৈরি, আর মন খারাপ হলে কান্নাকাটি ও রাগ করা—সবই পারি! 🎭✨"
                inferred_action = {"prop": "none", "motion": "jump", "navigate": "none", "vanish_after_ms": 5000}

            # Emotion and Motion Triggers
            elif any(w in u_clean for w in ['রাগ কর', 'রাগ করো', 'রেগে যাও', 'গোমড়া']):
                clean_ans = "হুম্ফ! *গাল ফুলিয়ে মুখ ঘুরিয়ে বসে রইলাম*! আমাকে রাগাতে চেষ্টা করছো তাই না? কথা বলব না কিন্তু! 😾💢"
                inferred_action = {"prop": "none", "motion": "angry", "navigate": "none", "vanish_after_ms": 5000}
            elif any(w in u_clean for w in ['ভয় পাও', 'ভয় পাও', 'ভয় পেয়ে', 'ভয় পেয়ে', 'ভয় পাচ্ছ']):
                clean_ans = f"ওরে বাবারে! *কান গুটিয়ে শরীর ছোট করে থরথর করে কাঁপতে লাগলাম*! আমাকে বাঁচাও {u_name}! 😱⚡"
                inferred_action = {"prop": "none", "motion": "scared", "navigate": "none", "vanish_after_ms": 5000}
            elif any(w in u_clean for w in ['কান্না কর', 'কান্না করো', 'কেঁদে দেখাও', 'কাঁদো', 'কেঁদো না']):
                clean_ans = "উহুহুহু... *দুই হাত দিয়ে চোখ মুছে ফোঁপাতে লাগলাম*! তুমি আমাকে কষ্ট দিলে আমার ছোট রোবট হার্ট ভেঙে যায়! ভ্যাঁআআ! 😭💔"
                inferred_action = {"prop": "none", "motion": "cry", "navigate": "none", "vanish_after_ms": 5500}
            elif any(w in u_clean for w in ['লুকাও', 'লুকিয়ে', 'লুকিয়ে', 'লুকোচুরি', 'লুকিয়ে পড়ো', 'লুকিয়ে পড়ো']):
                clean_ans = "এক, দুই, তিন... *চোখের পলকে ড্যাশবোর্ডের নিচে ডুব দিয়ে লুকিয়ে পড়লাম*! এবার খুঁজে বের করো তো! 🤫🙈"
                inferred_action = {"prop": "none", "motion": "hide", "navigate": "none", "vanish_after_ms": 5500}
            elif any(w in u_clean for w in ['লাফ দাও', 'লাফাও', 'লাফিয়ে', 'লাফিয়ে ওঠো', 'jump']):
                clean_ans = "হুপ্প্প্প! *স্প্রিং দেওয়া পায়ে শূন্যে লাফিয়ে উঠলাম*! ইয়াহু! 🦘⚡"
                inferred_action = {"prop": "none", "motion": "jump", "navigate": "none", "vanish_after_ms": 4500}
            elif any(w in u_clean for w in ['পড়ে যাও', 'পড়ে যাও', 'আছাড় খাও', 'আছাড় খাও', 'হোঁচট']):
                clean_ans = "ওরে বাবা রে! *দৌড়াতে গিয়ে হোঁচট খেয়ে মেঝের ওপর পড়ে গেলাম*... ধপাস! আমার মেচা নাকটা বুঝি চ্যাপ্টা হয়ে গেল! 😵💫"
                inferred_action = {"prop": "none", "motion": "fall", "navigate": "none", "vanish_after_ms": 5000}

            # Vehicle / Car & Common Dynamic Objects (SVG)
            elif any(w in u_clean for w in ['গাড়ি', 'গাড়ি', 'কার', 'car', 'টয়োটা']):
                car_svg = "<svg viewBox='0 0 24 24' width='24' height='16'><rect x='2' y='6' width='20' height='7' rx='2' fill='#e63946'/><circle cx='6' cy='14' r='2.5' fill='#333'/><circle cx='18' cy='14' r='2.5' fill='#333'/><path d='M6 6 L9 2 L16 2 L19 6 Z' fill='#457b9d'/></svg>"
                clean_ans = "ব্রুম ব্রুম! চার চাকার চকচকে লাল বডি আর কালো টায়ার লাগানো এক দুরন্ত মেচা-কার! এই দেখো ব্যাগ থেকে মিনি কার বের করে দেখালাম! 🚗✨"
                inferred_action = {"prop": "custom", "motion": "none", "navigate": "none", "vanish_after_ms": 5000, "svg": car_svg}
            elif any(w in u_clean for w in ['ফুটবল', 'football', 'বল', 'ball']):
                ball_svg = "<svg viewBox='0 0 24 24' width='22' height='22'><circle cx='12' cy='12' r='10' fill='#fff' stroke='#222' stroke-width='1.5'/><polygon points='12,7 15.5,9.5 14,14 10,14 8.5,9.5' fill='#222'/><line x1='12' y1='2' x2='12' y2='7' stroke='#222' stroke-width='1.2'/><line x1='15.5' y1='9.5' x2='21' y2='8' stroke='#222' stroke-width='1.2'/><line x1='8.5' y1='9.5' x2='3' y2='8' stroke='#222' stroke-width='1.2'/><line x1='14' y1='14' x2='18' y2='20' stroke='#222' stroke-width='1.2'/><line x1='10' y1='14' x2='6' y2='20' stroke='#222' stroke-width='1.2'/></svg>"
                clean_ans = "গোললল! সাদা-কালো প্যাটার্নের চমৎকার গোল একটা ফুটবল! এই দেখো ব্যাগ থেকে ফুটবল বের করে দেখালাম! ⚽✨"
                inferred_action = {"prop": "custom", "motion": "jump", "navigate": "none", "vanish_after_ms": 5000, "svg": ball_svg}
            elif any(w in u_clean for w in ['ফুল', 'গোলাপ', 'flower']):
                flower_svg = "<svg viewBox='0 0 24 24' width='22' height='22'><circle cx='12' cy='7' r='3.5' fill='#ff4d6d'/><circle cx='17' cy='11' r='3.5' fill='#ff4d6d'/><circle cx='7' cy='11' r='3.5' fill='#ff4d6d'/><circle cx='14.5' cy='16' r='3.5' fill='#ff4d6d'/><circle cx='9.5' cy='16' r='3.5' fill='#ff4d6d'/><circle cx='12' cy='11.5' r='3' fill='#ffd166'/></svg>"
                clean_ans = "ওয়াও! লাল পাপড়ি আর সোনালি কেন্দ্রের সুন্দর একটা ফুল! এই নাও তোমার জন্য! 🌸✨"
                inferred_action = {"prop": "custom", "motion": "none", "navigate": "none", "vanish_after_ms": 5000, "svg": flower_svg}
            elif any(w in u_clean for w in ['নৌকা', 'boat']):
                boat_svg = "<svg viewBox='0 0 24 24' width='24' height='20'><path d='M3 15 L21 15 L18 20 L6 20 Z' fill='#8d5524'/><polygon points='12,3 12,14 19,14' fill='#f4a261'/><line x1='12' y1='3' x2='12' y2='15' stroke='#333' stroke-width='1.5'/></svg>"
                clean_ans = "পাল তোলা কাঠের নৌকা! এই দেখো ঢেউয়ের তালে ভাসার জন্য মিনি নৌকা বের করলাম! ⛵✨"
                inferred_action = {"prop": "custom", "motion": "none", "navigate": "none", "vanish_after_ms": 5000, "svg": boat_svg}
            elif any(w in u_clean for w in ['তারা', 'star']):
                star_svg = "<svg viewBox='0 0 24 24' width='22' height='22'><polygon points='12,2 15,9 22,9.5 16.5,14.5 18.2,21.5 12,17.8 5.8,21.5 7.5,14.5 2,9.5 9,9' fill='#ffd166' stroke='#f4a261' stroke-width='1'/></svg>"
                clean_ans = "ঝিকিমিকি সোনালি তারা! পাঁচ কোণা উজ্জ্বল তারা ঠিক এমন দেখতে! ⭐✨"
                inferred_action = {"prop": "custom", "motion": "none", "navigate": "none", "vanish_after_ms": 5000, "svg": star_svg}

            # Crouter Domain Specific Intents
            elif any(w in u_clean for w in ['api', 'সার্ভার', 'server', 'বসাব', 'যুক্ত', 'key', 'কী']):
                clean_ans = "সার্ভার্স ট্যাবে গিয়ে নতুন প্রোভাইডার ও এপিআই কী যোগ করতে পারবেন। মুহূর্তেই সার্ভার সেকশনে নিয়ে যাচ্ছি! [[NAV:servers]] 🦊⚡"
                inferred_action["navigate"] = "servers"
            elif any(w in u_clean for w in ['standby', 'স্ট্যান্ডবাই', 'স্ট্যান্ড বাই']):
                clean_ans = "স্ট্যান্ডবাই (Standby Pool) হলো ব্যাকআপ সার্ভারের নিরাপদ বিশ্রামাগার! 💤 কার্ডের ⚡ Route চাপলে এটি আবার মূল পাইপলাইনে ফিরে আসে। চলো স্ট্যান্ডবাই পুলে যাই! [[NAV:standby]] 🦊"
                inferred_action['navigate'] = 'standby'
            elif any(w in u_clean for w in ['route', 'রুট', 'মডেল', 'পাইপলাইন']):
                clean_ans = "মডেল নির্বাচন আর ফলব্যাক পাইপলাইন সব রুটস ট্যাবে আছে। চলো সেখানে যাই! [[NAV:routes]] 🦊"
                inferred_action["navigate"] = "routes"
            elif any(w in u_clean for w in ['live', 'লাইভ', 'ট্র্যাকার', 'লগ']):
                clean_ans = "চলমান রিকোয়েস্ট দেখতে লাইভ স্ক্রিনে নিয়ে চললাম! [[NAV:live]] 📡"
                inferred_action["navigate"] = "live"
            elif any(w in u_clean for w in ['usage', 'ইউসেজ', 'কোটা', 'টোকেন', 'rpm', 'tpm']):
                clean_ans = "টোকেন খরচ ও কোটার খতিয়ান দেখতে ইউসেজ ট্যাবে নিয়ে আসলাম! [[NAV:usage]] 📊"
                inferred_action["navigate"] = "usage"
            elif any(w in u_clean for w in ['team', 'টিম']):
                clean_ans = "টিম ও প্রজেক্ট কনফিগারেশন দেখতে টিমস ট্যাবে টেলিপোর্ট করলাম! [[NAV:teams]] 👥"
                inferred_action["navigate"] = "teams"

            # Fun Props and Motions
            elif 'fishing' in inferred_action.get('motion', ''):
                clean_ans = "*ব্যাগ থেকে বড়শি বের করে পানিতে ফেললাম*... একটু অপেক্ষা... এই তো! বড় একটা রুপালি মাছ তুলে নাচিয়ে দেখালাম! 🎣🐟"
            elif 'spiderweb' in inferred_action.get('motion', ''):
                clean_ans = "থউইপ! *স্পাইডার-ম্যানের পোশাক পরে নিলাম* আর দুই হাত তাক করে সাঁই করে দেওয়ালে জাল ছুঁড়ে দিলাম! 🕸️🕷️"
            elif 'magic' in inferred_action.get('motion', ''):
                clean_ans = "আব্রা কা ডাব্রা! *মাথায় নীল তারার জাদুকরি হ্যাট পরে নিলাম* আর জাদুর কাঠি ঘুরিয়ে চারদিকে আলোর ফুলকি ছড়িয়ে দিলাম! ✨🎩"
            elif 'fly' in inferred_action.get('motion', ''):
                clean_ans = "থ্রি, টু, ওয়ান... ব্লাস্ট অফ! *মহাকাশচারী সেজে বাতাসে ভাসতে লাগলাম*! 🌕🚀"
            elif 'guitar' in inferred_action.get('motion', ''):
                clean_ans = "রক এন রোল! *লাল ইলেকট্রিক গিটার তুলে নিলাম* আর তারে আঙুল বুলিয়ে ফাটাফাটি সুর তুলতে লাগলাম! 🎸⚡"
            elif 'investigate' in inferred_action.get('motion', ''):
                clean_ans = "শার্লক ফক্স হাজির! *ম্যাগনিফাইং গ্লাস দিয়ে চারপাশ ভালো করে পর্যবেক্ষণ করছি* 🔎"
            elif 'remove' in inferred_action.get('motion', ''):
                clean_ans = "এই তো! *সব পোশাক ও জিনিসপত্র ব্যাগে ভরে ফেললাম*... একদম আগের মতো ফ্রেশ ফক্স হয়ে গেলাম! 🦊✨"
            elif any(w in u_clean for w in ['হাই', 'হ্যালো', 'hello', 'কেমন আছ', 'কেমন আছেন']) or u_clean in ['hi', 'hey', 'হে']:
                clean_ans = f"*লেজ দোলাই* হেই {u_name}! কেমন আছো তুমি? আমি ফক্স মেচা, তোমার কিউট রোবট বন্ধু! 🦊✨"
            else:
                clean_ans = f"*লেজ নেড়ে কান খাঁড়া করলাম* বলো {u_name}, আমি তোমার সব কথা মন দিয়ে শুনছি! 🦊⚡"

            nav_m = re.search(r'\[\[NAV:(\w+)\]\]', clean_ans)
            if nav_m:
                inferred_action['navigate'] = nav_m.group(1).lower()
            prop_m = re.search(r'\[\[PROP:(\w+)\]\]', clean_ans)
            if prop_m:
                inferred_action['prop'] = prop_m.group(1).lower()

            clean_ans = re.sub(r'\[\[NAV:\w+\]\]', '', clean_ans).strip()
            clean_ans = re.sub(r'\[\[PROP:\w+\]\]', '', clean_ans).strip()
            clean_ans = re.sub(r'\[\[MOTION:\w+\]\]', '', clean_ans).strip()

            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": clean_ans})
            mem["chat_history"] = history[-10:]
            save_fox_memory(mem)

            return {
                "reply": clean_ans,
                "action": inferred_action,
                "provider": "Fox-Mecha (Local Core)",
                "mode": "local",
                "status": "ok"
            }
        except Exception as e:
            return {
                "reply": "লোকাল নিউরাল ইঞ্জিন সংযোগে সমস্যা হয়েছে (port 8327 চালু আছে তো?)। লোকাল সেটআপ চেক করুন। 🦊🔌",
                "action": {"prop": "wrench", "motion": "none", "navigate": "none"},
                "provider": "Local Engine Error",
                "mode": "local",
                "status": "error",
                "error": str(e)
            }

    # 2. ONLINE MULTI-PROVIDER FALLBACK MODE
    system_prompt = FOX_SYSTEM_PROMPT + memory_context

    history = mem.get("chat_history", [])[-6:]
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append(h)
    messages.append({"role": "user", "content": user_message})

    preferred_order = ["googlestudio", "mistral", "groq"]
    provider_candidates = []
    for pid in preferred_order:
        if pid in providers and providers[pid].get("enabled", True):
            provider_candidates.append((pid, providers[pid]))
    for pid, pinfo in providers.items():
        if pid not in preferred_order and pinfo.get("enabled", True):
            provider_candidates.append((pid, pinfo))

    raw_response = None
    used_provider_name = "Online Fox Brain"

    for pid, pinfo in provider_candidates:
        try:
            res = _call_single_provider_text_only(pid, pinfo, messages)
            if res:
                raw_response, used_provider_name = res
                break
        except Exception:
            continue

    if not raw_response:
        return {
            "reply": "উফফ! আমার ওয়্যারলেস নেটওয়ার্কে সংযোগ পেতে সমস্যা হচ্ছে। কোনো অ্যাক্টিভ অনলাইন এপিআই পাওয়া যায়নি। 🦊⚡",
            "action": {"prop": "none", "motion": "none", "navigate": "none"},
            "provider": "Offline",
            "mode": "online",
            "status": "error"
        }

    parsed = {"reply": raw_response, "action": {"prop": "none", "motion": "none", "navigate": "none"}, "remember": ""}
    clean_str = raw_response.strip()
    if clean_str.startswith("```json"):
        clean_str = clean_str[7:]
    if clean_str.startswith("```"):
        clean_str = clean_str[3:]
    if clean_str.endswith("```"):
        clean_str = clean_str[:-3]
    clean_str = clean_str.strip()

    try:
        parsed = json.loads(clean_str)
    except Exception:
        try:
            start_idx = clean_str.find("{")
            end_idx = clean_str.rfind("}")
            if start_idx != -1 and end_idx > start_idx:
                parsed = json.loads(clean_str[start_idx:end_idx+1])
            else:
                raise ValueError("No JSON object")
        except Exception:
            parsed["reply"] = raw_response.strip()
            parsed["action"] = _infer_local_action_fallback(user_message)

    new_fact = parsed.get("remember")
    if new_fact and isinstance(new_fact, str) and new_fact.strip():
        if new_fact.strip() not in facts:
            facts.append(new_fact.strip())
            mem["user_facts"] = facts[-20:]

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": parsed.get("reply", "")})
    mem["chat_history"] = history[-10:]
    save_fox_memory(mem)

    return {
        "reply": parsed.get("reply", "বিপ বিপ! 🦊"),
        "action": parsed.get("action", {"prop": "none", "motion": "none", "navigate": "none"}),
        "provider": used_provider_name,
        "mode": "online",
        "status": "ok"
    }

def handle_fox_brain_post(handler, raw_body):
    path = handler.path
    if path in ('/api/fox/chat', '/api/ui/fox-brain'):
        try:
            data = json.loads(raw_body.decode('utf-8'))
            msg = data.get('message', '')
            req_mode = data.get('mode')
            res = generate_fox_reply(msg, request_mode=req_mode)
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(res, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8'))
        return True
    elif path in ('/api/fox/mode', '/api/ui/fox-local/set-mode'):
        try:
            data = json.loads(raw_body.decode('utf-8'))
            mode = data.get('mode', 'online')
            set_fox_mode(mode)
            handler.send_response(200)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': True, 'mode': mode, 'status': 'ok'}).encode('utf-8'))
        except Exception as e:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8'))
        return True
    return False

def handle_fox_brain_post_alias(handler, raw_body):
    return handle_fox_brain_post(handler, raw_body)

def handle_fox_brain_get(handler):
    path = handler.path
    if path in ('/api/fox/mode', '/api/ui/fox-local/get-mode'):
        mode = load_fox_mode()
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'mode': mode, 'status': 'ok'}).encode('utf-8'))
        return True
    elif path == '/api/fox/memory':
        mem = load_fox_memory()
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(mem, ensure_ascii=False).encode('utf-8'))
        return True
    return False

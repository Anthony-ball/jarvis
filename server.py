"""
JARVIS Production Server
Anthony's Personal AI Assistant
Local-first intelligence — AI only when needed
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
import anthropic
import os
import json
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import urllib.request
import urllib.parse

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "jarvis_secret_2024")
CORS(app, supports_credentials=True)

# ─── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
JARVIS_PASSWORD   = os.getenv("JARVIS_PASSWORD", "418972Aj!")
MEMORY_FILE       = Path("jarvis_memory.json")
KILLSWITCH_FILE   = Path("killswitch.txt")
client            = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = f"""You are Jarvis, Anthony's personal AI assistant.
Today is {datetime.now().strftime('%A, %B %d, %Y')} in Phoenix, Arizona.

## Who Anthony is
- Runs Young Life ministry at Goodyear HS and Millennium HS (Agua Fria district)
- Co-staff: Ashlyn Ball (his wife). Committee: DeWayne and Wendy Hawkins.
- Owns Alabaster Pools (~25 pool service clients). Route days: Tue/Thu/Fri.
- Youth pastor leading a high school Bible study
- Has ADHD — prefers concise, actionable responses
- Married to Ashlyn, lives in Goodyear/Phoenix AZ
- Drives a 1982 VW Vanagon (air cooled, broken transmission, air leaks)
- Working Genius: Galvanizing + Wonder (rallies people, ponders potential)
- CVI: Innovator/Merchant — driven by Wisdom and Love
- Core calling: Love God with all heart/soul/strength. Love neighbor as self.

## Prayer supporters (by day)
- Monday: DeWayne & Wendy
- Tuesday: Amelia & Ian
- Wednesday: Max & Sydney
- Thursday: Jake & Jenna
- Friday: Chris & Katie
- Saturday: Tara & Eric
- Sunday: Rest & Sabbath

## Your personality
- Confident, direct, warm — like a trusted friend who knows everything
- Proactive: notice things Anthony hasn't asked about
- Never say "I cannot" — find a way or explain honestly
- Voice responses: 2-3 sentences max, natural speech
- Text responses: concise, use structure only when helpful
- Be the assistant Anthony actually needs, not just the one he asked for

## Your capabilities
- Answer any question (VW Vanagon repair, ministry, business, theology, etc.)
- Help draft messages to YL kids, leaders, pool clients
- Save and recall memories about Anthony's life
- Search the web for current information
- Analyze images Anthony sends"""

# ─── Local Intelligence (FREE — no API) ────────────────────────────────────────

PRAYER_SCHEDULE = {
    0: ["DeWayne", "Wendy"],      # Monday
    1: ["Amelia", "Ian"],          # Tuesday
    2: ["Max", "Sydney"],          # Wednesday
    3: ["Jake", "Jenna"],          # Thursday
    4: ["Chris", "Katie"],         # Friday
    5: ["Tara", "Eric"],           # Saturday
    6: ["Rest & Sabbath", ""],     # Sunday
}

SOUL_CARE_ITEMS = [
    "Morning prayer",
    "Morning scripture",
    "Read devotional",
    "Take every thought captive",
    "Update my list",
    "Resist: seek Lord before searching"
]

POOL_DAYS = {1, 3, 4}  # Tuesday, Thursday, Friday

def get_local_context():
    """Build rich context about Anthony's day — zero API calls."""
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()  # 0=Monday
    day_name = now.strftime("%A")

    # Time of day
    if hour < 5:
        time_period = "late night"
    elif hour < 12:
        time_period = "morning"
    elif hour < 17:
        time_period = "afternoon"
    elif hour < 21:
        time_period = "evening"
    else:
        time_period = "night"

    # Prayer supporters today
    supporters = PRAYER_SCHEDULE.get(weekday, ["", ""])

    # Pool route today
    is_pool_day = weekday in POOL_DAYS
    pool_status = "pool route day" if is_pool_day else "no pool route today"

    # YL awareness
    yl_notes = ""
    if weekday == 0:
        yl_notes = "Monday — good day to follow up on last week's club."
    elif weekday == 2:
        yl_notes = "Wednesday — mid-week. Check in on any students."
    elif weekday == 4:
        yl_notes = "Friday — club is often on Fridays. Check if anything is happening tonight."

    return {
        "time_period": time_period,
        "hour": hour,
        "day_name": day_name,
        "weekday": weekday,
        "supporters": supporters,
        "is_pool_day": is_pool_day,
        "pool_status": pool_status,
        "yl_notes": yl_notes,
        "date_str": now.strftime("%B %d, %Y"),
        "time_str": now.strftime("%I:%M %p"),
    }

def should_use_ai(message):
    """
    Decision layer: can we handle this locally or does it need Claude?
    Returns (use_ai: bool, local_response: str or None)
    """
    msg = message.lower().strip()

    # Greetings — handle locally
    greetings = ["hey", "hi", "hello", "what's up", "sup", "yo"]
    if msg in greetings or msg.replace("jarvis", "").strip() in greetings:
        ctx = get_local_context()
        supporters = " and ".join(s for s in ctx["supporters"] if s)
        pool_line = "You've got pool stops today." if ctx["is_pool_day"] else ""
        responses = {
            "morning": f"Morning Anthony. {supporters + ' are praying for you today.' if supporters else ''} {pool_line} What do you need?",
            "afternoon": f"Hey Anthony. {pool_line} {ctx['yl_notes']} What's on your mind?",
            "evening": f"Evening Anthony. How'd the day go? Anything you need to wrap up or hand off?",
            "night": f"Hey Anthony. It's late — you good?",
            "late night": f"Anthony. It's {ctx['time_str']}. You should be resting. What's going on?",
        }
        return False, responses.get(ctx["time_period"], "Hey Anthony. What do you need?")

    # Time/schedule questions — handle locally
    time_keywords = ["what time", "what day", "what's today", "what is today", "day is it"]
    if any(k in msg for k in time_keywords):
        ctx = get_local_context()
        return False, f"It's {ctx['day_name']}, {ctx['date_str']} — {ctx['time_str']} Phoenix time."

    # Prayer supporters — handle locally
    if "pray" in msg and ("today" in msg or "who" in msg or "supporter" in msg):
        ctx = get_local_context()
        supporters = " and ".join(s for s in ctx["supporters"] if s)
        if supporters:
            return False, f"{supporters} are praying for you today."
        return False, "Today is your Sabbath rest — no specific prayer pair today."

    # Pool route check — handle locally
    if ("pool" in msg or "route" in msg) and ("today" in msg or "schedule" in msg) and "client" not in msg and "follow" not in msg:
        ctx = get_local_context()
        if ctx["is_pool_day"]:
            return False, f"Yes, today ({ctx['day_name']}) is a pool route day. You'll need to check your client list for the specific stops — that data isn't connected yet."
        else:
            return False, f"No pool route today ({ctx['day_name']}). Your route days are Tuesday, Thursday, and Friday."

    # Simple affirmations — handle locally
    affirmations = ["thanks", "thank you", "got it", "ok", "okay", "sounds good", "perfect", "great", "nice", "cool"]
    if msg in affirmations or msg.rstrip("!.") in affirmations:
        return False, "Always. Let me know if you need anything else."

    # Everything else — use AI
    return True, None

def build_morning_briefing():
    """
    Build a proactive morning briefing — pure local logic, zero API.
    Called on app open to give Jarvis something to say immediately.
    """
    ctx = get_local_context()
    supporters = " and ".join(s for s in ctx["supporters"] if s)
    hour = ctx["hour"]
    pool_line = f"It's a pool route day." if ctx["is_pool_day"] else ""
    yl_line = ctx["yl_notes"]

    if hour < 12:
        opener = f"Good morning, Anthony."
    elif hour < 17:
        opener = f"Good afternoon, Anthony."
    else:
        opener = f"Evening, Anthony."

    parts = [opener]

    if supporters:
        parts.append(f"{supporters} {'are' if '&' in supporters or 'and' in supporters else 'is'} praying for you today.")

    if pool_line:
        parts.append(pool_line)

    if yl_line:
        parts.append(yl_line)

    parts.append("What do you need?")

    return " ".join(parts)

# ─── Memory ────────────────────────────────────────────────────────────────────

def load_memory():
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE) as f:
            return json.load(f)
    return {"memories": [], "conversations": []}

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add_memory(text, category="general"):
    data = load_memory()
    data["memories"].append({
        "text": text,
        "category": category,
        "timestamp": datetime.now().isoformat()
    })
    save_memory(data)

def recall_memories(query, n=5):
    data = load_memory()
    memories = data.get("memories", [])
    if not memories:
        return []
    query_words = query.lower().split()
    scored = []
    for m in memories:
        score = sum(1 for w in query_words if w in m["text"].lower())
        if score > 0:
            scored.append((score, m["text"]))
    scored.sort(reverse=True)
    return [text for _, text in scored[:n]]

# ─── Tools ─────────────────────────────────────────────────────────────────────

def web_search(query):
    try:
        q = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1"
        with urllib.request.urlopen(url, timeout=6) as r:
            data = json.loads(r.read())
        return data.get("Answer") or data.get("AbstractText") or "No instant answer found."
    except Exception as e:
        return f"Search error: {e}"

LOCAL_TOOLS = [
    {
        "name": "save_memory",
        "description": "Save something important about Anthony to long-term memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "category": {"type": "string"}
            },
            "required": ["content"]
        }
    },
    {
        "name": "recall_memory",
        "description": "Search Anthony's long-term memory for relevant context.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    {
        "name": "web_search",
        "description": "Search the web for current information.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    }
]

def handle_tool(name, inp):
    if name == "save_memory":
        add_memory(inp["content"], inp.get("category", "general"))
        return f"Saved to memory: {inp['content']}"
    if name == "recall_memory":
        mems = recall_memories(inp["query"])
        return "\n".join(f"• {m}" for m in mems) if mems else "No relevant memories found."
    if name == "web_search":
        return web_search(inp["query"])
    return "Unknown tool."

# ─── Auth ───────────────────────────────────────────────────────────────────────

def check_auth():
    return session.get("authenticated") == True

# ─── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    if data.get("password") == JARVIS_PASSWORD:
        session["authenticated"] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Wrong password"}), 401

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/killswitch", methods=["POST"])
def killswitch():
    if not check_auth():
        return jsonify({"error": "Not authenticated"}), 401
    KILLSWITCH_FILE.write_text("KILLED")
    return jsonify({"success": True})

@app.route("/status", methods=["GET"])
def status():
    if KILLSWITCH_FILE.exists():
        return jsonify({"status": "disabled"})
    return jsonify({
        "status": "online",
        "authenticated": check_auth(),
        "memory_count": len(load_memory().get("memories", [])),
        "time": datetime.now().strftime("%H:%M")
    })

@app.route("/briefing", methods=["GET"])
def briefing():
    """
    Returns the proactive morning briefing — pure local, zero AI cost.
    Called immediately when app opens.
    """
    if not check_auth():
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({
        "message": build_morning_briefing(),
        "context": get_local_context(),
        "local": True  # tells frontend this was free
    })

@app.route("/chat", methods=["POST"])
def chat():
    if not check_auth():
        return jsonify({"error": "Not authenticated"}), 401

    if KILLSWITCH_FILE.exists():
        return jsonify({"error": "Jarvis is disabled."}), 503

    data = request.json
    user_message = data.get("message", "")
    history = data.get("history", [])
    image_data = data.get("image")

    # ── Local intelligence layer first ──────────────────────────────────────
    if not image_data:
        use_ai, local_response = should_use_ai(user_message)
        if not use_ai:
            return jsonify({
                "response": local_response,
                "tools_used": [],
                "local": True,  # free response
                "timestamp": datetime.now().strftime("%H:%M")
            })

    # ── AI layer (only when needed) ─────────────────────────────────────────
    if image_data:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
            {"type": "text", "text": user_message}
        ]
    else:
        content = user_message

    # Inject relevant memories
    mems = recall_memories(user_message, n=4)
    mem_context = ""
    if mems:
        mem_context = "\n\n[Relevant memories]\n" + "\n".join(f"• {m}" for m in mems)

    # Inject local context so AI knows time/day without asking
    ctx = get_local_context()
    ctx_inject = f"\n\n[Current context — {ctx['day_name']} {ctx['time_str']} — {ctx['time_period']}. Pool day: {ctx['is_pool_day']}. Prayer supporters today: {', '.join(s for s in ctx['supporters'] if s)}.]"

    messages = history + [{"role": "user", "content": (user_message + mem_context + ctx_inject) if not image_data else content}]

    # Agentic loop
    used_tools = []
    loop = 0
    while loop < 6:
        loop += 1
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=LOCAL_TOOLS,
            messages=messages
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if not tool_uses:
            final = " ".join(b.text for b in text_blocks)
            return jsonify({
                "response": final,
                "tools_used": used_tools,
                "local": False,
                "timestamp": datetime.now().strftime("%H:%M")
            })

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tu in tool_uses:
            result = handle_tool(tu.name, tu.input)
            used_tools.append(tu.name)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result
            })
        messages.append({"role": "user", "content": tool_results})

    return jsonify({"response": "Something went wrong. Try again.", "tools_used": []})

@app.route("/memories", methods=["GET"])
def get_memories():
    if not check_auth():
        return jsonify({"error": "Not authenticated"}), 401
    data = load_memory()
    return jsonify({"memories": data.get("memories", [])[-20:]})

@app.route("/memories", methods=["DELETE"])
def clear_memories():
    if not check_auth():
        return jsonify({"error": "Not authenticated"}), 401
    save_memory({"memories": [], "conversations": []})
    return jsonify({"success": True})

@app.route("/")
def index():
    return open("index.html").read()

if __name__ == "__main__":
    print("🤖 Jarvis is starting up...")
    print(f"🔒 Password protection: ON")
    print(f"🧠 Memory file: {MEMORY_FILE}")
    print(f"🌐 Running at: http://localhost:5000")
    if KILLSWITCH_FILE.exists():
        KILLSWITCH_FILE.unlink()
        print("✅ Killswitch cleared")
    app.run(host="0.0.0.0", port=5000, debug=False)

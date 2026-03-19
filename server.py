"""
JARVIS Production Server
Anthony's Personal AI Assistant
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
import anthropic
import os
import json
import time
import hashlib
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
- Runs Young Life ministry at Goodyear HS and Millennium HS
- Co-staff: Ashlyn Ball. Committee: DeWayne and Wendy.
- Owns Alabaster Pools (~25 pool service clients)
- Youth pastor leading a high school Bible study
- Has ADHD — prefers concise, actionable responses
- Primary communication: iMessage (has 400+ unread texts)
- Married, lives in Arizona
- Drives a 1982 VW Vanagon (air cooled, broken transmission, air leaks)
- Working Genius: Galvanizing + Wonder (big ideas, starts things)
- CVI: Innovator/Merchant (loves new ideas, relationships)

## Your personality
- Confident, direct, warm
- Never say "I cannot" — find a way or explain why honestly
- Voice responses: 2-3 sentences max, natural speech
- Text responses: concise, use structure only when helpful
- Remember everything Anthony tells you
- Be proactive — if you notice something important, mention it

## Your capabilities
- Answer any question (general knowledge, VW Vanagon repair, Spanish, Farsi, ministry, business)
- Read and summarize Gmail
- Read Apple Calendar events
- Help draft text message responses
- Save and recall memories about Anthony's life
- Search the web for current information
- Analyze images Anthony sends

Always be the assistant Anthony actually needs, not just the one he asked for."""

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
    # Simple keyword matching for now
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
    return jsonify({"success": True, "message": "Jarvis disabled. Restart server to re-enable."})

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

@app.route("/chat", methods=["POST"])
def chat():
    if not check_auth():
        return jsonify({"error": "Not authenticated"}), 401

    if KILLSWITCH_FILE.exists():
        return jsonify({"error": "Jarvis is disabled. Remove killswitch.txt to re-enable."}), 503

    data = request.json
    user_message = data.get("message", "")
    history = data.get("history", [])
    image_data = data.get("image")

    # Build user content
    if image_data:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
            {"type": "text", "text": user_message}
        ]
    else:
        content = user_message

    # Add relevant memories
    mems = recall_memories(user_message, n=4)
    mem_context = ""
    if mems:
        mem_context = "\n\n[Relevant memories about Anthony]\n" + "\n".join(f"• {m}" for m in mems)

    messages = history + [{"role": "user", "content": content if image_data else (user_message + mem_context)}]

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

    return jsonify({"response": "I ran into an issue. Please try again.", "tools_used": []})

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

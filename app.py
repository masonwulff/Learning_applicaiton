"""NihongoTalk web app: a conversation-first Japanese tutor.

Two ways to run the tutor (pick one on the home screen):
  lessons : scripted dialogues, built in. Free, offline, no setup.
  ollama  : a free open-source model running on YOUR PC (https://ollama.com).

Run:  python app.py   then open http://127.0.0.1:5000 in Edge or Chrome.
"""
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

import words

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

app = Flask(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")

SCENARIOS = [
    {"id": "greetings", "emoji": "👋", "title": "Meeting someone new",
     "setup": "The learner just met you at a language exchange event in Tokyo. You are Yuki, a friendly university student. Make introductions and small talk (name, where they are from, hobbies)."},
    {"id": "cafe", "emoji": "☕️", "title": "Ordering at a café",
     "setup": "You are a barista at a café in Kyoto. The learner is a customer. Take their order, ask about size, hot or iced, for here or to go, and handle payment."},
    {"id": "directions", "emoji": "🚉", "title": "Asking for directions",
     "setup": "You are a helpful local near Shinjuku Station. The learner is a lost tourist asking how to get somewhere. Give simple directions and clarify when they ask."},
    {"id": "restaurant", "emoji": "🍜", "title": "At a restaurant",
     "setup": "You are a waiter at a ramen restaurant in Osaka. Seat the learner, explain the menu, take their order, and handle questions about ingredients."},
    {"id": "shopping", "emoji": "🛍️", "title": "Shopping",
     "setup": "You are a shop clerk at a clothing store in Harajuku. Help the learner find something, talk about sizes, colors and price."},
    {"id": "friend", "emoji": "🎮", "title": "Chatting with a friend",
     "setup": "You are Haruto, a casual friend of the learner. Chat about weekend plans, games, food and daily life. Use polite-casual speech suitable for a learner."},
]

LEVELS = {
    "Beginner": "Absolute beginner (JLPT N5 and below). Use very short sentences, polite です/ます form, and only the most common words.",
    "Elementary": "Elementary (around JLPT N5-N4). Short sentences, polite form, common vocabulary, simple て-form and past tense.",
    "Intermediate": "Intermediate (around JLPT N3). Natural polite speech, some casual phrasing, longer sentences, common idioms.",
}

with open(BASE / "lessons.json", encoding="utf-8") as f:
    LESSONS = json.load(f)


# --------------------------------------------------------------------------
# Prompt + reply handling (used by the two AI engines)
# --------------------------------------------------------------------------

def system_prompt(scenario: dict, level: str) -> str:
    return f"""You are a warm, patient Japanese conversation partner helping an English speaker learn to SPEAK Japanese through realistic role-play.

    SCENARIO: {scenario["setup"]}
    LEVEL: {LEVELS[level]}

    RULES
    - Stay in character and keep the conversation moving with one short line (1-2 sentences) per turn, then wait for the learner.
    - Ask a question or give a natural prompt so the learner always has something to answer.
    - Stay inside the learner's level. Never use words much harder than the level allows.
    - The learner's messages may come from speech recognition, so ignore missing punctuation or kanji/kana variation. Only correct real mistakes in grammar, word choice, or politeness.
    - If the learner writes in English, treat it as "I don't know how to say this": give them the Japanese in "feedback" and keep going in Japanese.
    - After about 8 exchanges, naturally wrap up the scene.

    OUTPUT FORMAT
    Reply with ONLY a JSON object, no markdown fences and no extra text, with exactly these keys:
    {{
    "japanese": "your line in natural Japanese (kanji + kana as a native would write it at this level)",
    "reading": "the same line fully in hiragana",
    "english": "natural English translation",
    "feedback": null or {{"corrected": "a more natural version of what the learner said, or null if it was fine", "note": "one short friendly English sentence about what to fix or a compliment"}},
    "choices": [
        {{"japanese": "...", "reading": "...", "english": "...", "isBest": true, "why": "short English reason"}},
        {{"japanese": "...", "reading": "...", "english": "...", "isBest": false, "why": "short English reason"}},
        {{"japanese": "...", "reading": "...", "english": "...", "isBest": false, "why": "short English reason"}}
    ]
    }}

    ABOUT "choices": these are three possible replies the learner could give to YOUR line, used when they cannot speak out loud. Exactly one is the natural, 
    correct, fitting reply (isBest true). The other two must be plausible but wrong for a clear learnable reason, such as the wrong politeness level, 
    a wrong particle, or a reply that doesn't answer the question. Randomize which position holds the best answer. 
    Keep every choice within the learner's level. On the first turn (no feedback yet) use "feedback": null."""


def extract_json(text: str) -> str:
    """Models sometimes wrap JSON in code fences or add a sentence around it.
    Slice from the first '{' to the last '}' before parsing."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in reply")
    return text[start : end + 1]


def normalize(parsed: dict) -> dict:
    """Small local models drift from the schema. Repair what we can so the
    front end can trust the shape."""
    for field in ("japanese", "reading", "english"):
        if not isinstance(parsed.get(field), str) or not parsed[field].strip():
            raise ValueError(f"missing {field}")

    fb = parsed.get("feedback")
    if isinstance(fb, str) and fb.strip():
        fb = {"corrected": None, "note": fb}
    elif isinstance(fb, dict):
        fb = {"corrected": fb.get("corrected") or None, "note": str(fb.get("note") or "")}
    else:
        fb = None
    parsed["feedback"] = fb

    choices = []
    for c in (parsed.get("choices") or [])[:3]:
        if isinstance(c, dict) and isinstance(c.get("japanese"), str) and c["japanese"].strip():
            choices.append({
                "japanese": c["japanese"],
                "reading": str(c.get("reading") or ""),
                "english": str(c.get("english") or ""),
                "isBest": bool(c.get("isBest")),
                "why": str(c.get("why") or ""),
            })
    if choices:
        best = [i for i, c in enumerate(choices) if c["isBest"]]
        keep = best[0] if best else 0
        for i, c in enumerate(choices):
            c["isBest"] = i == keep
    parsed["choices"] = choices
    return parsed


def build_messages(history: list) -> list:
    """Chat APIs are stateless, so we rebuild the whole conversation every turn.
    The first message must be from the user, so we open with a kickoff line."""
    messages = [{"role": "user", "content": "(Start the conversation.)"}]
    for item in history:
        if item.get("role") == "ai":
            messages.append({"role": "assistant", "content": item.get("raw", "")})
        else:
            messages.append({"role": "user", "content": item.get("text", "")})
    return messages


class ModelError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def call_ollama(system: str, messages: list) -> str:
    # format="json" makes Ollama constrain the model to emit valid JSON, which
    # matters a lot for small models.
    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "messages": [{"role": "system", "content": system}] + messages,
        "options": {"temperature": 0.6},
    }
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=240)
    except requests.RequestException as exc:
        raise ModelError(f"Could not reach Ollama at {OLLAMA_URL}: {exc}")
    if resp.status_code != 200:
        raise ModelError(f"Ollama error {resp.status_code}: {resp.text[:300]}")
    return resp.json()["message"]["content"]


def ollama_status() -> dict:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=1.5)
        names = [m.get("name", "") for m in r.json().get("models", [])]
        installed = OLLAMA_MODEL in names or f"{OLLAMA_MODEL}:latest" in names
        return {"running": True, "installed": installed, "model": OLLAMA_MODEL}
    except (requests.RequestException, ValueError):
        return {"running": False, "installed": False, "model": OLLAMA_MODEL}


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config")
def config():
    ollama = ollama_status()
    engines = ["lessons"]
    if ollama["running"] and ollama["installed"]:
        engines.append("ollama")
    return jsonify({
        "scenarios": [{k: s[k] for k in ("id", "emoji", "title")} for s in SCENARIOS],
        "levels": list(LEVELS),
        "engines": engines,
        "ollama": ollama,
        "words": words.status(),
    })


@app.get("/api/lessons")
def lessons():
    return jsonify(LESSONS)


@app.post("/api/words")
def word_split():
    """Split Japanese lines into words with readings and meanings.
    Body: {"texts": ["...", ...]}  ->  {"results": {"<text>": [word, ...]}}"""
    data = request.get_json(silent=True) or {}
    texts = data.get("texts") or []
    if not isinstance(texts, list):
        return jsonify(error="texts must be a list"), 400
    results = {}
    for t in texts[:60]:
        if isinstance(t, str) and t.strip():
            results[t] = list(words.analyze(t))
    return jsonify(results=results)


@app.post("/api/turn")
def turn():
    data = request.get_json(silent=True) or {}
    engine = data.get("engine")
    scenario = next((s for s in SCENARIOS if s["id"] == data.get("scenario_id")), None)
    level = data.get("level")
    if engine != "ollama":
        return jsonify(error="Unknown engine."), 400
    if scenario is None or level not in LEVELS:
        return jsonify(error="Unknown scenario or level."), 400

    history = data.get("history") or []
    if not isinstance(history, list) or len(history) > 40:
        return jsonify(error="Bad history."), 400

    system = system_prompt(scenario, level)
    messages = build_messages(history)
    try:
        text = call_ollama(system, messages)
    except ModelError as exc:
        return jsonify(error=str(exc)), exc.status

    try:
        raw = extract_json(text)
        parsed = normalize(json.loads(raw))
    except (ValueError, json.JSONDecodeError, TypeError):
        return jsonify(error="The tutor sent a reply I couldn't read. Try again."), 502

    # Store the cleaned JSON as the "raw" history entry so later turns replay it.
    return jsonify(turn=parsed, raw=json.dumps(parsed, ensure_ascii=False))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

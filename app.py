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
from flask import Flask, Response, jsonify, render_template, request

import tts
import words

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

app = Flask(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_MAX_TOKENS = 900   # hard cap per reply; see call_ollama

LEVELS = {
    "Beginner": "Absolute beginner (JLPT N5 and below). Use very short sentences, polite です/ます form, and only the most common words.",
    "Elementary": "Elementary (around JLPT N5-N4). Short sentences, polite form, common vocabulary, simple て-form and past tense.",
    "Intermediate": "Intermediate (around JLPT N3). Natural polite speech, some casual phrasing, longer sentences, common idioms.",
}

CHAR_DIR = BASE / "characters"
MAX_RANK = 10


def load_characters():
    """Read every characters/*.json file, in filename order.

    Files are re-read on every request, so editing a character and refreshing
    the page is enough: no server restart needed. A broken file is skipped
    and reported, so one typo doesn't take down the whole app."""
    chars, problems, seen = [], [], set()
    for path in sorted(CHAR_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}: line {exc.lineno}, column {exc.colno}: {exc.msg}")
            continue
        missing = [k for k in ("name", "name_en", "personality") if not data.get(k)]
        if missing:
            problems.append(f"{path.name}: missing {', '.join(missing)}")
            continue
        # The id comes from the file name without its number: 01-yuki.json -> yuki.
        cid = path.stem.split("-", 1)[1] if "-" in path.stem and path.stem.split("-", 1)[0].isdigit() else path.stem
        if cid in seen:
            problems.append(f"{path.name}: another file already uses the id '{cid}'")
            continue
        seen.add(cid)
        bad_ep = []
        episodes = []
        for i, ep in enumerate(data.get("episodes") or []):
            steps = ep.get("steps") or []
            ok = steps and ep.get("closing") and all(
                isinstance(st.get("ai"), dict) and isinstance(st.get("answer"), dict) and isinstance(st.get("wrong"), list)
                for st in steps)
            if ok:
                ep.setdefault("rank", 0)
                ep.setdefault("title", f"Conversation {i + 1}")
                episodes.append(ep)
            else:
                bad_ep.append(str(i + 1))
        if bad_ep:
            problems.append(f"{path.name}: skipped episode(s) {', '.join(bad_ep)} (each needs steps with ai/answer/wrong, and a closing line)")
        data["episodes"] = episodes
        data["facts"] = [str(f) for f in (data.get("facts") or [])][:MAX_RANK]
        data["voice"] = data.get("voice") or {}
        data["id"] = cid
        data["file"] = f"characters/{path.name}"
        chars.append(data)
    return chars, problems


def find_character(cid):
    return next((c for c in load_characters()[0] if c["id"] == cid), None)


# --------------------------------------------------------------------------
# Prompt + reply handling (used by the AI engine)
# --------------------------------------------------------------------------

def relationship(rank: int) -> str:
    if rank <= 1:
        return "You have only just met the learner. Be friendly but a little reserved, like with a new acquaintance."
    if rank <= 4:
        return "You know the learner a bit now. Be warmer and more relaxed, and show some of your personality."
    if rank <= 7:
        return "You are good friends with the learner. Be open, joke around, and talk about your own life."
    return "You are close friends with the learner and trust them. You share personal worries and dreams."


def system_prompt(ch: dict, level: str, rank: int) -> str:
    facts = ch.get("facts") or []
    known = facts[:rank]
    nxt = facts[rank] if rank < len(facts) else None
    known_txt = "\n".join(f"    - {f}" for f in known) or "    - Nothing yet. You have just met."
    share_txt = (f"Somewhere in this conversation, if it fits naturally, bring up this about yourself in simple Japanese: {nxt}"
                 if nxt else "The learner already knows you very well. Talk like old friends.")
    return f"""You are {ch["name_en"]} ({ch["name"]}), {ch.get("role", "")}. You are a character in a Japanese speaking-practice app, talking with an English speaker who is learning Japanese.

    SETTING: {ch.get("setting", "")}
    YOUR PERSONALITY: {ch["personality"]}
    HOW YOU TALK: {ch.get("speech_style", "Natural, friendly Japanese.")}
    RELATIONSHIP: Bond rank {rank} of {MAX_RANK}. {relationship(rank)}
    THINGS THE LEARNER ALREADY KNOWS ABOUT YOU (stay consistent with these):
{known_txt}
    THIS TIME: {share_txt}
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
        # A normal reply is ~250-400 tokens. Small models sometimes get stuck
        # emitting endless whitespace inside JSON mode; num_predict stops that
        # after a few seconds instead of letting it run for minutes. Ollama
        # answers one request at a time, so one runaway reply would otherwise
        # make every later reply wait in line behind it.
        "options": {"temperature": 0.6, "num_predict": OLLAMA_MAX_TOKENS},
    }
    try:
        # 90s leaves room for loading the model into memory on the first turn.
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=90)
    except requests.Timeout:
        raise ModelError("The local AI took too long to answer. Try again.", 504)
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
        "levels": list(LEVELS),
        "engines": engines,
        "ollama": ollama,
        "words": words.status(),
        "voicevox": tts.status(),
    })


@app.get("/api/characters")
def characters():
    chars, problems = load_characters()
    for ch in chars:
        ch["voice_credit"] = tts.credit(ch["voice"].get("voicevox"))
    return jsonify(characters=chars, problems=problems)


@app.post("/api/tts")
def speak():
    """Read a line aloud with VOICEVOX.
    Body: {"text": "...", "character_id": "yuki" (optional)} -> audio/wav.
    Without a character, the default announcer voice is used."""
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()
    if not text or len(text) > 300:
        return jsonify(error="text must be 1-300 characters"), 400
    cfg = None
    if data.get("character_id"):
        ch = find_character(data["character_id"])
        cfg = (ch or {}).get("voice", {}).get("voicevox")
    try:
        wav = tts.synthesize(text, cfg)
    except tts.TTSError as exc:
        return jsonify(error=str(exc)), 503
    return Response(wav, mimetype="audio/wav", headers={"Cache-Control": "private, max-age=86400"})


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
    ch = find_character(data.get("character_id"))
    level = data.get("level")
    try:
        rank = max(0, min(MAX_RANK, int(data.get("rank") or 0)))
    except (TypeError, ValueError):
        rank = 0
    if engine != "ollama":
        return jsonify(error="Unknown engine."), 400
    if ch is None or level not in LEVELS:
        return jsonify(error="Unknown character or level."), 400

    history = data.get("history") or []
    if not isinstance(history, list) or len(history) > 40:
        return jsonify(error="Bad history."), 400

    system = system_prompt(ch, level, rank)
    messages = build_messages(history)
    # A cut-off or garbled reply is usually a one-off, so try once more
    # before showing an error.
    parsed = None
    for _ in range(2):
        try:
            text = call_ollama(system, messages)
        except ModelError as exc:
            return jsonify(error=str(exc)), exc.status
        try:
            parsed = normalize(json.loads(extract_json(text)))
            break
        except (ValueError, json.JSONDecodeError, TypeError):
            continue
    if parsed is None:
        return jsonify(error="The tutor sent a reply I couldn't read. Try again."), 502

    # Store the cleaned JSON as the "raw" history entry so later turns replay it.
    return jsonify(turn=parsed, raw=json.dumps(parsed, ensure_ascii=False))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

"""Realistic voices through VOICEVOX (https://voicevox.hiroshiba.jp).

VOICEVOX is a free Japanese text-to-speech program. While its app is open it
runs a small local server (port 50021), and this module asks that server to
read lines aloud. Nothing leaves your PC.

If VOICEVOX isn't running, the browser's built-in voices are used instead.

Each character's file can name the VOICEVOX voice it wants:

    "voicevox": {"speakers": ["玄野武宏/ノーマル", "白上虎太郎"],
                 "speed": 1.0, "pitch": 0.0, "intonation": 1.0}

"speakers" is tried in order. "Name/Style" picks a style, a bare "Name" uses
that speaker's first style. Names are matched against what your installed
VOICEVOX actually has, so a missing voice just falls through to the next.
"""
import os
import threading
import time
from collections import OrderedDict

import requests

VOICEVOX_URL = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")

# Used for lines that aren't spoken by a character (your own answers, word
# lookups), and as the last fallback for everyone.
DEFAULT_SPEAKERS = ["雨晴はう/ノーマル", "四国めたん/ノーマル", "ずんだもん/ノーマル"]

_lock = threading.Lock()
_speakers = {"at": 0.0, "list": None}     # cached /speakers response
_audio = OrderedDict()                     # (style_id, settings, text) -> wav bytes
_AUDIO_MAX = 300


class TTSError(Exception):
    pass


def _get_speakers(force=False):
    """The installed VOICEVOX voices, cached for a minute."""
    with _lock:
        fresh = time.time() - _speakers["at"] < 60
        if _speakers["list"] is not None and fresh and not force:
            return _speakers["list"]
    try:
        r = requests.get(f"{VOICEVOX_URL}/speakers", timeout=2)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        data = None
    with _lock:
        _speakers["list"], _speakers["at"] = data, time.time()
    return data


def status():
    data = _get_speakers()
    if data is None:
        return {"running": False, "voices": 0}
    return {"running": True, "voices": len(data)}


def resolve(wanted):
    """Turn ["Name/Style", "Name", ...] into (style_id, speaker_name, style_name), or None."""
    data = _get_speakers() or []
    for item in list(wanted or []) + DEFAULT_SPEAKERS:
        item = str(item).strip()
        # Some names contain "/" themselves (小夜/SAYO), so try the whole
        # string as a name first, then split off the style at the LAST "/".
        name, style = item, ""
        if not any(s.get("name") == item for s in data):
            name, _, style = item.rpartition("/")
            name = name or item
        sp = next((s for s in data if s.get("name") == name.strip()), None)
        if not sp or not sp.get("styles"):
            continue
        st = next((s for s in sp["styles"] if s.get("name") == style.strip()), None) if style else None
        st = st or sp["styles"][0]
        return st["id"], sp["name"], st["name"]
    return None


def synthesize(text, cfg=None):
    """Return WAV bytes for `text` in the voice described by `cfg`."""
    cfg = cfg or {}
    picked = resolve(cfg.get("speakers"))
    if picked is None:
        raise TTSError("VOICEVOX isn't running, or has none of the requested voices.")
    style_id = picked[0]

    def num(key, lo, hi, default):
        try:
            return min(hi, max(lo, float(cfg.get(key, default))))
        except (TypeError, ValueError):
            return default

    speed = num("speed", 0.5, 2.0, 1.0)
    pitch = num("pitch", -0.15, 0.15, 0.0)
    intonation = num("intonation", 0.0, 2.0, 1.0)
    key = (style_id, speed, pitch, intonation, text)
    with _lock:
        if key in _audio:
            _audio.move_to_end(key)
            return _audio[key]

    try:
        q = requests.post(f"{VOICEVOX_URL}/audio_query", params={"text": text, "speaker": style_id}, timeout=20)
        q.raise_for_status()
        query = q.json()
        query.update(speedScale=speed, pitchScale=pitch, intonationScale=intonation,
                     prePhonemeLength=0.05, postPhonemeLength=0.1)
        s = requests.post(f"{VOICEVOX_URL}/synthesis", params={"speaker": style_id}, json=query, timeout=60)
        s.raise_for_status()
    except requests.RequestException as exc:
        _get_speakers(force=True)   # maybe it was closed; re-check next time
        raise TTSError(f"VOICEVOX error: {exc}")

    wav = s.content
    with _lock:
        _audio[key] = wav
        while len(_audio) > _AUDIO_MAX:
            _audio.popitem(last=False)
    return wav


def credit(cfg=None):
    """The 'VOICEVOX:Name' credit for the voice that would be used."""
    picked = resolve((cfg or {}).get("speakers"))
    return f"VOICEVOX:{picked[1]}" if picked else None

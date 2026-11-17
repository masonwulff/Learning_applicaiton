"""Split Japanese text into clickable words and look each one up.

Japanese doesn't put spaces between words, so finding the words is a real
step. We use fugashi (a MeCab wrapper) with the UniDic dictionary. For every
token it gives us:
  - the surface form as written:            来
  - the part of speech:                     動詞 (verb)
  - the dictionary form (lemma):            来る
  - the reading in katakana:                キ

Then we group tokens into the units a learner thinks of as one word:
  来 + まし + た        ->  来ました   (look up 来る, form "polite past")
  探し + て + い + ます  ->  探しています (look up 探す, form "is doing")
  交換 + し + ませ + ん  ->  交換しません (look up 交換する / 交換)
and also merge fixed phrases the dictionary knows as a whole, like
いらっしゃいませ or よろしくお願いします.

Meanings come from data/dictionary.json, built from JMdict (EDRDG, CC BY-SA 4.0).
Particles and endings get short hand-written explanations instead, because a
dictionary definition of は ("topic marker") is less useful than a plain one.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

try:
    import fugashi
    _TAGGER = fugashi.Tagger()
except Exception:            # fugashi or unidic-lite not installed
    _TAGGER = None

_DATA = Path(__file__).parent / "data" / "dictionary.json"
_ENTRIES: list = []
_INDEX: dict = {}


def _load() -> None:
    if _ENTRIES or not _DATA.exists():
        return
    with open(_DATA, encoding="utf-8") as f:
        _ENTRIES.extend(json.load(f)["entries"])
    for i, (kanji, kana, _pos, _gl) in enumerate(_ENTRIES):
        for form in kanji + kana:
            _INDEX.setdefault(form, []).append(i)


_load()

KANJI = re.compile(r"[㐀-䶿一-鿿々]")
JAPANESE = re.compile(r"[぀-ヿ㐀-䶿一-鿿々ー]")


def has_kanji(s: str) -> bool:
    return bool(KANJI.search(s))


def hira(s: str) -> str:
    """Katakana -> hiragana (leaves the long-vowel mark ー alone)."""
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s or "")


# --- plain-English labels -------------------------------------------------

POS_LABEL = {
    "名詞": "Noun", "代名詞": "Pronoun", "動詞": "Verb", "形容詞": "Adjective (い-adjective)",
    "形状詞": "Adjective (な-adjective)", "副詞": "Adverb", "連体詞": "Adjective (comes before a noun)",
    "接続詞": "Conjunction", "感動詞": "Interjection", "助詞": "Particle", "助動詞": "Ending",
    "接頭辞": "Prefix", "接尾辞": "Suffix", "phrase": "Phrase",
}
# Which JMdict part-of-speech codes match each UniDic class (used to pick
# between entries that share a spelling, e.g. さん "Mr./Ms." vs 三 "three").
POS_MATCH = {
    "名詞": {"n", "pn", "num", "ctr"}, "代名詞": {"pn", "n"}, "動詞": {"v", "vs"},
    "形容詞": {"adj-i"}, "形状詞": {"adj-na"}, "副詞": {"adv"}, "接尾辞": {"suf", "ctr"},
    "接頭辞": {"pref"}, "感動詞": {"int", "exp"}, "接続詞": {"conj"}, "助詞": {"prt"},
}

# Short explanations for grammar words. These beat dictionary definitions.
GRAMMAR = {
    "は": ["Topic marker: \"as for ...\". Pronounced wa."],
    "が": ["Subject marker: points out who or what does something.", "but (between two sentences)"],
    "を": ["Object marker: the thing the action is done to. Pronounced o."],
    "に": ["to, at, in: a destination, a point in time, or who receives something"],
    "で": ["at, in: where an action happens", "by, with: the means used"],
    "へ": ["toward (a direction). Pronounced e."],
    "と": ["and (joining nouns)", "with (someone)"],
    "も": ["also, too"],
    "の": ["Links nouns, like 's or \"of\": 私の本 = my book"],
    "か": ["Question marker: turns a sentence into a question"],
    "ね": ["\"right?\" or \"isn't it?\": invites agreement"],
    "よ": ["Adds emphasis, like \"you know\" or \"I'm telling you\""],
    "から": ["from", "because"],
    "まで": ["until, as far as"],
    "や": ["and (listing some examples)"],
    "けど": ["but, although"],
    "って": ["Quotes something, or \"speaking of ...\""],
    "です": ["is, am, are (polite)"],
    "でした": ["was, were (polite)"],
    "ですか": ["is it ...? (polite question)"],
    "だ": ["is, am, are (casual)"],
    "でしょう": ["probably; right? (polite)"],
    "ください": ["please (give me / do this for me)"],
    "じゃあ": ["well then, in that case"],
    "じゃ": ["well then, in that case"],
}

# Endings on a verb or adjective, checked longest first.
FORMS = [
    ("ませんでした", "Polite past negative: did not"),
    ("ていません", "Polite negative of ~ている: is not doing / has not"),
    ("ています", "Polite ~ている: is doing, or a continuing state"),
    ("でいます", "Polite ~ている: is doing, or a continuing state"),
    ("てください", "Please do ... (polite request)"),
    ("でください", "Please do ... (polite request)"),
    ("ましょう", "Polite \"let's ...\""),
    ("ましょうか", "Polite \"shall we ...?\" or \"shall I ...?\""),
    ("ましたか", "Polite past question: did ...?"),
    ("ました", "Polite past: did"),
    ("ません", "Polite negative: does not, will not"),
    ("ますか", "Polite question: do ...? will ...?"),
    ("ます", "Polite present: does, will do"),
    ("ている", "~ている: is doing, or a continuing state"),
    ("ていた", "~ていた: was doing"),
    ("なかった", "Past negative: did not"),
    ("かった", "Past: was"),
    ("くない", "Negative: is not"),
    ("ない", "Negative: does not"),
    ("たい", "Want to ..."),
    ("たら", "If / when ..."),
    ("て", "て-form: joins actions (\"and\"), or used before another word"),
    ("で", "て-form: joins actions (\"and\"), or used before another word"),
    ("た", "Past"),
    ("だ", "Past"),
]
CFORM = {"意志推量形": "Volitional: \"let's ...\" or \"I'll ...\"", "命令形": "Command form"}

# Counters after a number. The general dictionary meaning (名 = "name") is
# wrong in 二名 or 何名, so these win when a counter follows a number.
COUNTERS = {
    "名": "Counter for people (polite): 二名 = two people",
    "人": "Counter for people: 三人 = three people",
    "つ": "General counter for things: 二つ = two (things)",
    "個": "Counter for small objects",
    "枚": "Counter for flat things: tickets, shirts, paper",
    "本": "Counter for long thin things: bottles, pens, trains",
    "杯": "Counter for cups and glasses of drink",
    "回": "Counter for times: 二回 = twice",
    "時": "o'clock: 三時 = three o'clock",
    "分": "minutes: 五分 = five minutes",
    "歳": "years old",
    "階": "floor of a building",
    "番": "number (in a series): 一番 = number one",
}

# A noun made from a verb (探し from 探す) usually isn't in the dictionary on
# its own. Map the stem's last kana to the dictionary-form ending.
STEM_TO_DICT = {"し": "す", "き": "く", "ぎ": "ぐ", "ち": "つ", "り": "る", "び": "ぶ",
                "み": "む", "い": "う", "に": "ぬ"}


# --- dictionary lookup ----------------------------------------------------

def lookup(keys, reading=None, pos1=None):
    """Return the best entry for the first key that exists."""
    want = POS_MATCH.get(pos1, set())
    for key in keys:
        if not key or key not in _INDEX:
            continue
        best, best_score = None, -1
        for rank, i in enumerate(_INDEX[key]):
            kanji, kana, pos, _gl = _ENTRIES[i]
            score = 0
            if reading and reading in kana:
                score += 4
            if want & set(pos):
                score += 2
            score -= rank * 0.01           # entries are pre-sorted by commonness
            if score > best_score:
                best, best_score = _ENTRIES[i], score
        if best:
            return best
    return None


def _entry_view(entry):
    kanji, kana, pos, glosses = entry
    return {"head": (kanji or kana)[0], "headRd": kana[0] if kana else "", "senses": glosses}


# --- tokenizing -----------------------------------------------------------

def _clean_lemma(lemma):
    """UniDic writes loanword lemmas like 'コーヒー-coffee'. Split that."""
    if not lemma:
        return None, None
    if "-" in lemma and not lemma.startswith("-"):
        jp, en = lemma.split("-", 1)
        return jp, en
    return lemma, None


def _tokens(text):
    out = []
    for w in _TAGGER(text):
        f = w.feature
        lemma, en = _clean_lemma(f.lemma)
        out.append({
            "s": w.surface,
            "pos1": f.pos1, "pos2": f.pos2, "pos3": f.pos3,
            "lemma": lemma or w.surface,
            "en": en,
            "lemmaRd": hira(f.lForm) if f.lForm else None,
            "kana": hira(f.kana) if f.kana else w.surface,
            "cForm": f.cForm or "",
        })
    return out


def _is_punct(t):
    return t["pos1"] in ("補助記号", "記号", "空白") or not JAPANESE.search(t["s"])


def _phrase_at(toks, i):
    """Longest run of 2+ tokens starting at i that the dictionary lists as a
    set phrase (e.g. いらっしゃいませ, よろしくお願いします)."""
    if toks[i]["pos1"] in ("助詞", "助動詞") or _is_punct(toks[i]):
        return 0, None
    for j in range(min(len(toks), i + 6), i + 1, -1):
        span = toks[i:j]
        if any(_is_punct(t) for t in span):
            continue
        surface = "".join(t["s"] for t in span)
        # Compound nouns the splitter breaks apart: 日本 + 語 -> 日本語.
        compound = all(t["pos1"] in ("名詞", "接頭辞", "接尾辞") for t in span)
        for i_ in _INDEX.get(surface, []):
            if compound or "exp" in _ENTRIES[i_][2] or "int" in _ENTRIES[i_][2]:
                return j - i, _ENTRIES[i_]
    return 0, None


def _group(toks):
    chunks = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if _is_punct(t):
            chunks.append({"t": t["s"], "w": False})
            i += 1
            continue

        n, phrase = _phrase_at(toks, i)
        if phrase:
            span = toks[i:i + n]
            compound = all(x["pos1"] in ("名詞", "接頭辞", "接尾辞") for x in span)
            chunks.append({"t": "".join(x["s"] for x in span), "w": True, "kind": "phrase",
                           "rd": "".join(x["kana"] for x in span), "entry": phrase,
                           "pos1": "名詞" if compound else "phrase"})
            i += n
            continue

        prev_tok = toks[i - 1] if i > 0 else None
        c = {"t": t["s"], "w": True, "head": t, "tail": "", "rd": t["kana"], "lemma": t["lemma"],
             "lemmaRd": t["lemmaRd"], "pos1": t["pos1"], "toks": [t],
             "afterNumber": bool(prev_tok and (prev_tok["pos2"] == "数詞" or prev_tok["s"] == "何"))}
        i += 1

        # A prefix like お/ご belongs to the next word: お願い, ご注文.
        if t["pos1"] == "接頭辞" and i < len(toks) and not _is_punct(toks[i]) and toks[i]["pos1"] not in ("助詞", "助動詞"):
            nxt = toks[i]
            c.update(t=c["t"] + nxt["s"], rd=c["rd"] + nxt["kana"], head=nxt, lemma=nxt["lemma"],
                     lemmaRd=nxt["lemmaRd"], pos1=nxt["pos1"], prefix=t["s"])
            c["toks"].append(nxt)
            i += 1

        # Noun + する is one verb: 交換 + しません -> 交換しません.
        if (c["pos1"] == "名詞" and "サ変" in (c["head"]["pos3"] or "") and i < len(toks)
                and toks[i]["pos1"] == "動詞" and toks[i]["lemma"] in ("為る", "する")):
            s = toks[i]
            c.update(t=c["t"] + s["s"], rd=c["rd"] + s["kana"], suru=True)
            c["toks"].append(s)
            i += 1

        # Conjugation: endings, て, and helper verbs (いる, ください) after て.
        if c["pos1"] in ("動詞", "形容詞", "助動詞") or c.get("suru"):
            while i < len(toks):
                n_ = toks[i]
                prev = c["toks"][-1]
                ends_te = prev["s"] in ("て", "で") and prev["pos1"] == "助詞"
                if n_["pos1"] == "助動詞" and n_["lemma"] == "です" and prev["pos1"] != "助動詞":
                    break        # keep です as its own word: おもしろい | です
                elif n_["pos1"] == "助動詞":
                    pass
                elif n_["pos1"] == "助詞" and n_["pos2"] == "接続助詞" and n_["s"] in ("て", "で") and prev["pos1"] in ("動詞", "形容詞", "助動詞"):
                    pass
                elif n_["pos1"] == "動詞" and n_["pos2"] == "非自立可能" and ends_te:
                    pass
                else:
                    break
                c["t"] += n_["s"]
                c["rd"] += n_["kana"]
                c["toks"].append(n_)
                i += 1
            first = c["toks"][1 if c.get("prefix") else 0]
            c["tail"] = c["t"][len((c.get("prefix") or "") + first["s"]):]
            if c.get("suru"):
                c["tail"] = c["t"][len((c.get("prefix") or "") + first["s"]):]
        chunks.append(c)
    return chunks


def _describe(c):
    """Turn a grouped chunk into what the popover shows."""
    if not c["w"]:
        return {"t": c["t"], "w": False}
    out = {"t": c["t"], "w": True, "rd": c["rd"] if has_kanji(c["t"]) else "",
           "pos": POS_LABEL.get(c["pos1"], ""), "senses": [], "base": None, "baseRd": None, "form": None}

    if c.get("kind") == "phrase":
        out["senses"] = c["entry"][3]
        return out

    head = c["head"]
    # Grammar words: particles, です, ください ...
    for key in (c["t"], head["s"]):
        if key in GRAMMAR and c["pos1"] in ("助詞", "助動詞", "動詞", "接続詞", "感動詞"):
            out["senses"] = GRAMMAR[key]
            if c["t"] in ("ください",):
                out["pos"] = "Request"
            return out

    lemma = c["lemma"]
    keys = []
    if c.get("suru"):
        keys.append(lemma + "する")
        out["base"], out["baseRd"] = lemma + "する", (head["lemmaRd"] or "") + "する"
        out["pos"] = "Verb (noun + する)"
    # Dictionary form first: the written stem of a conjugated word (来 in 来ました)
    # is often a different word on its own (来 = "next").
    if c.get("prefix"):
        keys.append(c["prefix"] + head["s"])
    keys += [lemma, head["s"]]
    if head["lemmaRd"]:
        keys.append(head["lemmaRd"])
    if head["s"] in COUNTERS and "助数詞" in (head["pos3"] or "") and c.get("afterNumber"):
        out["senses"], out["pos"] = [COUNTERS[head["s"]]], "Counter"
        return out
    entry = lookup(keys, head["lemmaRd"], c["pos1"])
    if not entry and c["pos1"] == "名詞" and head["s"][-1:] in STEM_TO_DICT:
        # お探し -> 探す, 持ち帰り -> 持ち帰る
        verb = head["s"][:-1] + STEM_TO_DICT[head["s"][-1]]
        entry = lookup([verb, head["s"] + "る"], None, "動詞")
        if entry:
            out["base"] = (entry[0] or entry[1])[0]
            out["baseRd"] = entry[1][0] if entry[1] and has_kanji(out["base"]) else None
            out["pos"] = "Noun (from a verb)"
    if entry:
        out["senses"] = entry[3]
    elif head.get("en"):
        out["senses"] = [head["en"]]                  # loanword or name: 'ジョン-John'
    if head["pos2"] == "固有名詞":
        out["pos"] = "Name"

    # Show the dictionary form when the word on screen is conjugated.
    if not c.get("suru") and c["pos1"] in ("動詞", "形容詞", "助動詞") and lemma and lemma != c["t"]:
        out["base"] = lemma
        out["baseRd"] = head["lemmaRd"] if has_kanji(lemma) else None
        # UniDic sometimes lists a kanji lemma for a word usually written in
        # kana (下さる for ください). Keep the learner's spelling in view.
        if entry and not has_kanji(head["s"]) and has_kanji(lemma) and head["lemmaRd"]:
            out["base"], out["baseRd"] = head["lemmaRd"], None
        if out["base"] == c["t"]:
            out["base"] = out["baseRd"] = None

    tail = c.get("tail") or ""
    for ending, label in FORMS:
        if tail.endswith(ending) and tail:
            out["form"] = label
            break
    if not out["form"] and c["toks"][-1]["cForm"].split("-")[0] in CFORM and c["pos1"] == "動詞":
        out["form"] = CFORM[c["toks"][-1]["cForm"].split("-")[0]]
    return out


# --- fallback when fugashi isn't installed --------------------------------

def _greedy(text):
    """Longest dictionary match at each position. No conjugation handling,
    but enough to keep the feature working."""
    out, i = [], 0
    while i < len(text):
        if not JAPANESE.search(text[i]):
            j = i
            while j < len(text) and not JAPANESE.search(text[j]):
                j += 1
            out.append({"t": text[i:j], "w": False})
            i = j
            continue
        for j in range(min(len(text), i + 10), i, -1):
            piece = text[i:j]
            if j == i + 1 and piece not in GRAMMAR and "぀" <= piece <= "ゟ":
                out.append({"t": piece, "w": False})     # lone kana ending: don't guess
                i = j
                break
            if piece in GRAMMAR or piece in _INDEX or j == i + 1:
                senses = GRAMMAR.get(piece) or (_ENTRIES[_INDEX[piece][0]][3] if piece in _INDEX else [])
                rd = _ENTRIES[_INDEX[piece][0]][1][0] if piece in _INDEX and _ENTRIES[_INDEX[piece][0]][1] else ""
                out.append({"t": piece, "w": True, "rd": rd if has_kanji(piece) else "", "pos": "",
                            "senses": senses, "base": None, "baseRd": None, "form": None})
                i = j
                break
    return out


@lru_cache(maxsize=2048)
def analyze(text: str) -> tuple:
    text = text[:300]
    if _TAGGER is None:
        return tuple(_greedy(text))
    return tuple(_describe(c) for c in _group(_tokens(text)))


def status() -> dict:
    return {"tokenizer": _TAGGER is not None, "dictionary": len(_ENTRIES)}

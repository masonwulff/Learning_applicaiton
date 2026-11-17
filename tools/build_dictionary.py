"""Build data/dictionary.json from JMdict.

You don't need to run this: the app ships with the built file. It's here so
you can see where the data comes from, or rebuild with more words.

    pip download --no-deps jamdict-data      # ~54 MB, contains jamdict.db.xz
    (extract the archive, then decompress jamdict.db.xz)
    python tools/build_dictionary.py path/to/jamdict.db

Word data: JMdict, (c) Electronic Dictionary Research and Development Group,
used under CC BY-SA 4.0. https://www.edrdg.org/edrdg/licence.html
"""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# JMdict "priority" tags mark common words. These are the ones jmdict's own
# "common" flag uses.
COMMON = {"news1", "ichi1", "spec1", "spec2", "gai1"}
# Everyday set phrases a beginner meets on day one. Some aren't tagged common in
# JMdict, so include them by name.
EXTRA_FORMS = {
    "はじめまして", "初めまして", "よろしくお願いします", "よろしくおねがいします", "宜しくお願いします",
    "ごちそうさまでした", "ご馳走様でした", "ごちそうさま", "ご馳走様", "そうですか", "そうですね",
    "おやすみなさい", "お休みなさい", "いってきます", "行ってきます", "いってらっしゃい", "行ってらっしゃい",
    "ただいま", "おかえりなさい", "お帰りなさい", "すみません", "済みません", "ごめんなさい", "御免なさい",
    "どういたしまして", "おはようございます", "こんにちは", "こんばんは", "さようなら", "お疲れ様です",
    "お疲れさまです", "失礼します", "お邪魔します", "気をつけて", "またね", "じゃあね", "お待たせしました",
    "かしこまりました", "畏まりました", "いただきます", "頂きます", "お元気ですか", "元気", "ごゆっくり",
    "お先に", "お大事に", "おめでとう", "おめでとうございます", "ありがとう", "有難う", "いいですね",
    "よろしく", "宜しく", "お願い", "どうぞ", "どうも", "いらっしゃい", "わかりました", "分かりました",
}
MAX_SENSES = 3
MAX_GLOSSES = 4

# Shorten JMdict's long part-of-speech descriptions.
POS_SHORT = [
    ("expressions", "exp"), ("interjection", "int"), ("noun", "n"),
    ("pronoun", "pn"), ("adjective (keiyoushi)", "adj-i"), ("adjectival nouns", "adj-na"),
    ("adverb", "adv"), ("conjunction", "conj"), ("particle", "prt"), ("suffix", "suf"),
    ("prefix", "pref"), ("counter", "ctr"), ("numeric", "num"), ("Godan verb", "v"),
    ("Ichidan verb", "v"), ("Kuru verb", "v"), ("suru verb", "vs"), ("verb", "v"),
]


def short_pos(text: str) -> str:
    for needle, code in POS_SHORT:
        if needle.lower() in text.lower():
            return code
    return ""


def main(db_path: str, out_path: str) -> None:
    c = sqlite3.connect(db_path)

    prio = defaultdict(int)          # idseq -> number of common tags
    for idseq, tag in c.execute("select k.idseq, p.text from Kanji k join KJP p on p.kid = k.ID"):
        if tag in COMMON:
            prio[idseq] += 1
    for idseq, tag in c.execute("select k.idseq, p.text from Kana k join KNP p on p.kid = k.ID"):
        if tag in COMMON:
            prio[idseq] += 1
    keep = set(prio)
    for table in ("Kanji", "Kana"):
        for (idseq,) in c.execute(
            f"select idseq from {table} where text in ({','.join('?' * len(EXTRA_FORMS))})", list(EXTRA_FORMS)
        ):
            keep.add(idseq)

    kanji, kana = defaultdict(list), defaultdict(list)
    for idseq, text in c.execute("select idseq, text from Kanji order by ID"):
        if idseq in keep:
            kanji[idseq].append(text)
    for idseq, text in c.execute("select idseq, text from Kana order by ID"):
        if idseq in keep:
            kana[idseq].append(text)

    senses = defaultdict(list)       # idseq -> [(sid, [glosses])]
    gloss_by_sid = defaultdict(list)
    for sid, text in c.execute("select sid, text from SenseGloss where lang = 'eng'"):
        gloss_by_sid[sid].append(text)
    pos_by_sid = defaultdict(list)
    for sid, text in c.execute("select sid, text from pos"):
        pos_by_sid[sid].append(text)
    for sid, idseq in c.execute("select ID, idseq from Sense order by ID"):
        if idseq in keep and gloss_by_sid.get(sid):
            senses[idseq].append(sid)

    entries = []
    for idseq in sorted(keep, key=lambda i: (-prio[i], i)):
        sids = senses.get(idseq)
        if not sids:
            continue
        pos = []
        for sid in sids:
            for p in pos_by_sid.get(sid, []):
                code = short_pos(p)
                if code and code not in pos:
                    pos.append(code)
        glosses = ["; ".join(gloss_by_sid[sid][:MAX_GLOSSES]) for sid in sids[:MAX_SENSES]]
        entries.append([kanji.get(idseq, []), kana.get(idseq, []), pos, glosses])

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "source": "JMdict (EDRDG), CC BY-SA 4.0, common entries",
            "entries": entries,
        }, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {len(entries)} entries to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python tools/build_dictionary.py path/to/jamdict.db [out.json]")
    out = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parent.parent / "data" / "dictionary.json")
    main(sys.argv[1], out)

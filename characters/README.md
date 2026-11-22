# Characters

Each file here is one person you can talk to. Edit a file, save it, and
refresh the page. You don't need to restart the app.

- **Order:** files appear on the menu in filename order (`01-…`, `02-…`).
- **Id:** the id is the filename without its number (`01-yuki.json` → `yuki`).
  Your bond progress is saved under that id, so renaming `yuki` resets it.
  Changing only the number is safe.
- **New person:** copy a file, give it a new name (for example
  `11-kaito.json`), and edit it.
- **Mistakes:** if a file has a typo (a missing comma or quote is the usual
  cause), the app skips it and shows a red message saying which line to fix.

## Fields

| Field | What it does |
|---|---|
| `name`, `name_en` | Japanese and English name, shown on the menu and their dialog boxes. |
| `emblem` | One kanji shown in their red diamond. |
| `role`, `tagline` | A short description and a one-line hook for the menu. |
| `setting` | Where and how you know them. Used by the AI tutor. |
| `personality` | **Who they are.** The AI tutor plays them this way. |
| `speech_style` | **How they talk:** politeness, favorite phrases, casual or formal. Used by the AI tutor. |
| `voice` | How they sound. See below. |
| `facts` | 10 things you learn about them, one per bond rank. Fact 1 unlocks at rank 1, and so on. The AI tutor also uses the next locked fact as something they might bring up. |
| `episodes` | Scripted conversations for Guided lessons. See below. |

The AI tutor reads `personality`, `speech_style`, `setting` and `facts`.
The scripted episodes use their own written lines.

## Voice

There are two kinds of voice:

- **VOICEVOX**, used when the free VOICEVOX app is open. These voices are
  much more natural.
- **The browser's own voice**, used when VOICEVOX isn't open.

### VOICEVOX

```json
"voicevox": {"speakers": ["玄野武宏/ノーマル", "雀松朱司"], "speed": 0.95, "pitch": 0.0, "intonation": 1.0}
```

- `speakers`: voices to try, in order, written as `Name/Style` or just
  `Name`. The names are on the VOICEVOX website or in the app's character
  list.
- `speed`: 0.5 to 2, where 1 is normal.
- `pitch`: -0.15 to 0.15, where 0 is normal.
- `intonation`: 0 to 2. Higher sounds more expressive, lower sounds flatter.

VOICEVOX's terms ask you to credit the voice as `VOICEVOX:<name>` if you
share audio. The app shows these credits in Settings.

### Browser voice

```json
"voice": {"gender": "female", "prefer": ["Aoi", "Nanami", "Haruka"], "pitch": 1.15, "rate": 1.05}
```

- `prefer`: voice names to try, in order. The first one installed is used.
  - Edge: Nanami, Aoi, Mayu, Shiori, Keita, Daichi, Naoki.
  - Windows: Haruka, Ayumi, Sayaka, Ichiro.
- `gender`: the fallback if none of the `prefer` voices are installed.
- `pitch`: 0 to 2, where 1 is normal. Higher sounds younger.
- `rate`: 0.5 to 2, where 1 is normal speed.
- `sample` (optional): the line played by "Hear their voice" in their profile.

Even if your computer has only one Japanese voice, different `pitch` and
`rate` values keep people sounding different.

## Episodes

```json
{
  "title": "The live show", "title_jp": "ライブの話",
  "rank": 3,
  "steps": [
    {
      "ai":     {"jp": "…", "rd": "(all hiragana)", "en": "…"},
      "answer": {"jp": "…", "rd": "…", "en": "…"},
      "wrong": [
        {"jp": "…", "rd": "…", "en": "…", "why": "Why it's wrong, in one sentence."},
        {"jp": "…", "rd": "…", "en": "…", "why": "…"}
      ]
    }
  ],
  "closing": {"jp": "…", "rd": "…", "en": "…"}
}
```

- `rank`: the bond rank needed to unlock this episode. Use 0 for one that's
  available from the start.
- `steps`: what they say (`ai`), the right reply (`answer`), and two wrong
  replies (`wrong`) for tap mode.
- `closing`: their last line.

## Bond points

- +1 for each reply you get right first time (tap) or say correctly (speak).
- +2 for finishing a conversation.
- With the AI tutor, every reply counts.

The points needed for each rank are in `RANK_AT` near the top of the
`<script>` in `templates/index.html`.

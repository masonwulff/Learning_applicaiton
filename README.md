# 日本語トーク (NihongoTalk), free web version

Conversation-first Japanese practice. You role-play real situations (café,
directions, restaurant...), speak your replies, and get corrections. Streaks
and a daily XP goal keep you consistent. When you can't talk, flip to
**Quiet mode** and answer with multiple choice instead.

## Run it on Windows

  1. python -m venv venv
  2. venv\Scripts\activate
  3. pip install -r requirements.txt
  4. python app.py
  5. ollama pull qwen2.5:3b

## People and bonds (絆)

You practice by talking to 10 people, each with their own personality and
voice. Every conversation raises your bond with that person. Each new rank
(up to 10) reveals something about them in their profile (press **P** on the
menu), and higher ranks unlock new conversations.

To change someone's personality, voice or lines, edit their file in
`characters/` and refresh the page. `characters/README.md` explains every
field and how to add a new person.

## Realistic voices (optional)

Install the free [VOICEVOX](https://voicevox.hiroshiba.jp/) app and keep it
open while you practice. Each person then speaks with their own natural
voice. Without it, the app uses your browser's Japanese voice. You can turn
VOICEVOX off in Settings.

## How it fits together

- `characters/` holds one JSON file per person: personality, voice, the facts
  you unlock, and their scripted conversations. The lesson engine runs
  entirely in the browser.
- `app.py` (Flask) serves the page and talks to Ollama for the
  free local AI tutor.
- `words.py` splits Japanese into words (fugashi + UniDic), groups
  conjugations together, and looks words up in `data/dictionary.json`.
- `data/dictionary.json` holds about 22,000 common words from JMdict.
  `tools/build_dictionary.py` shows how it was built.
- `templates/index.html` is the whole front end. The browser provides speech
  recognition (ja-JP) and the Japanese voice, so nothing extra to install.
- Streak, XP, bond ranks and settings live in your browser's localStorage.
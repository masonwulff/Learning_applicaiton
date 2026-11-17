# 日本語トーク (NihongoTalk), free web version

Conversation-first Japanese practice. You role-play real situations (café,
directions, restaurant...), speak your replies, and get corrections. Streaks
and a daily XP goal keep you consistent. When you can't talk, flip to
**Quiet mode** and answer with multiple choice instead.

## Run it on Windows

  python -m venv venv
  venv\Scripts\activate
  pip install -r requirements.txt
  python app.py

  ollama pull qwen2.5:3b

## How it fits together

- `lessons.json` holds the scripted conversations. The lesson engine runs
  entirely in the browser.
- `app.py` (Flask) serves the page and talks to Ollama for the
  free local AI tutor.
- `words.py` splits Japanese into words (fugashi + UniDic), groups
  conjugations together, and looks words up in `data/dictionary.json`.
- `data/dictionary.json` holds about 22,000 common words from JMdict.
  `tools/build_dictionary.py` shows how it was built.
- `templates/index.html` is the whole front end. The browser provides speech
  recognition (ja-JP) and the Japanese voice, so nothing extra to install.
- Streak, XP and settings live in your browser's localStorage.
# Contributing to Dread Eater 🦥

Small, kind contributions are very welcome (Hacktoberfest included).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py test      # all tests must pass; Ollama is mocked
python run.py           # start the app
```

## Ground rules

- Keep it local-first: no telemetry, no cloud calls, server stays bound to localhost.
- Never hard-code absolute paths; use `backend/paths.py`.
- Add or update tests for behaviour changes.
- One focused change per pull request.

## Ideas

- More languages for the UI and the sloth's prompts
- Extra micro-step templates for the offline fallback
- Accessibility improvements (keyboard flow, reduced motion)
- Docs, screenshots, and bug reports

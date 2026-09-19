# Notes for coding agents

- Python package in `src/jev_drive`, React UI in `frontend/`. The UI build output in `src/jev_drive/web/dist` is committed so the package runs without Node.
- Install: `python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`
- Test: `pytest` (offline, no API key, no cost).
- Run: `jev-drive serve --open` with `OPENROUTER_API_KEY` in the environment, or `jev-drive serve --provider typesafe --open` with `TYPESAFE_API_KEY` (whitelisted access from typesafe.ai). Without a key use `--no-jev`, which starts the rule driver.
- Check a running server: `curl -s http://127.0.0.1:8765/state`. `t` must grow between calls.
- UI: `cd frontend && npm ci && npm run build`, then restart the server. `npm run lint` must be clean.
- Never write API keys to files. Pass them as environment variables only.
- `runs/` holds local logs, recordings and response caches. It is ignored by git and must stay out of commits.
- The code has no comments by choice. Explain behaviour in README.md instead.

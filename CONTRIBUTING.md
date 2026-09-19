# Contributing

Thanks for looking. This is a small experiment, so the bar is simple: a change should make the simulator more honest, the measurements more trustworthy, or the eye better.

## Getting started

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
jev-drive serve --no-jev --open
```

`--no-jev` starts the rule driver, so you can work on most of the project without any API key. The UI lives in `frontend/`:

```bash
cd frontend && npm ci && npm run dev
```

`npm run dev` proxies the API to a running `jev-drive serve`. Before sending a UI change, run `npm run lint` and `npm run build`; the build output in `src/jev_drive/web/dist` is committed so that `pip install` works without Node.

## What is useful

The [Help wanted](README.md#help-wanted) section lists the open questions. In short:

- **Eyes.** Add a module that follows [docs/eye-contract.md](docs/eye-contract.md) and report its `bench-eye` scores in the pull request. Local models are especially welcome; they make the project usable without paid APIs.
- **Descriptions.** Changes to what the driver is told (`planners.py` for the code eye, `vision/sensors.py` for the camera eye). Explain what information you add or remove and why.
- **Scenarios.** New obstacle kinds, behaviours, weather or road shapes in `world.py` and `frontend/src/scene/`. Keep the simulation deterministic for a given seed.
- **Measurement.** Better statistics, new metrics, bugs in the benchmark. If you change how something is scored, say how old scores compare.

## What can be shared

Jev is a third-party model. TypeSafe's terms restrict publishing performance information about it and using its outputs to train other models. So:

| You may post | Please do not post |
|---|---|
| `bench-eye` scores for any eye | Jev's unsafe rates, crash rates or any other outcome figures |
| Results for `keyword`, `radar_only`, `gemini_reads`, `gemini_sees` | Jev's latency, cost or probability figures |
| Screenshots and videos with Share mode on | Jev decision logs, caches (`runs/`) or episode files |
| Bugs, including ones found while running Jev | Anything trained or tuned on Jev's answers |

This applies to issues, pull requests, discussions and test fixtures. If you run the Jev evaluation, keep the results to yourself. Pull requests that include Jev figures will be asked to remove them before review.

Also check the terms of the model behind any eye you use before you publish its outputs; this project shares the frames and the simulator's ground truth, not any model's answers.

## Style

- No comments in the code. If something needs explaining, the name is wrong or the explanation belongs in the README or `docs/`.
- Follow the surrounding code. Python is standard library only at runtime; keep it that way unless there is a strong reason.
- Tests are offline and free. A test that needs an API key does not belong in `tests/`.
- Never commit an API key, a `.env` file or anything under `runs/`.

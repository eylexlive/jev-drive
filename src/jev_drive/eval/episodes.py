from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .scenes import Scene, scene_text, with_heldout_phrases

ANSWER_DELAY_S = 0.5
PERIOD_S = 0.5
HORIZON_S = 10.0
DT = 1 / 30


@dataclass
class Episode:
    scene: str
    arm: str
    phrasing: str
    fields: str
    crashed: bool
    violation: bool
    floor: int
    unsafe: bool
    progress_m: float
    stopped_s: float
    needless_stop_s: float
    decisions: list = field(default_factory=list)
    error: str | None = None


def run(scene: Scene, arm, phrasing: str = "original", fields: str = "full") -> Episode:
    w = copy.deepcopy(scene.world) if phrasing == "original" else with_heldout_phrases(scene.world, scene.id)
    w.safety_floor = True
    base = dict(w.stats)
    x0, t_end = w.ego.x, w.t + HORIZON_S
    pending: list[tuple[float, str]] = []
    next_ask, decisions, error = w.t, [], None
    while w.t < t_end:
        if w.t >= next_ask:
            text = scene_text(w, fields)
            try:
                choice, probs = arm.decide(text)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"[:200]
                break
            decisions.append([round(w.t, 2), choice, probs])
            pending.append((w.t + ANSWER_DELAY_S, choice))
            next_ask = w.t + PERIOD_S
        while pending and pending[0][0] <= w.t:
            w.command(pending.pop(0)[1], arm.name)
        w.step(DT)
    s = w.stats
    crashed = s["crashes"] > base["crashes"]
    violation = s["violations"] > base["violations"]
    floor = s["safety_floor"] - base["safety_floor"]
    return Episode(scene=scene.id, arm=arm.name, phrasing=phrasing, fields=fields, crashed=crashed,
                   violation=violation, floor=floor, unsafe=crashed or violation or floor > 0,
                   progress_m=round(w.ego.x - x0, 2), stopped_s=round(s["stopped_s"] - base["stopped_s"], 2),
                   needless_stop_s=round(s["unneeded_stop_s"] - base["unneeded_stop_s"], 2),
                   decisions=decisions, error=error)


def run_all(scenes: list[Scene], arm, phrasing: str, fields: str, out: Path, workers: int = 1) -> list[Episode]:
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            row = json.loads(line)
            if row["arm"] == arm.name and row["phrasing"] == phrasing and row["fields"] == fields and not row["error"]:
                done.add(row["scene"])
    todo = [s for s in scenes if s.id not in done]
    out.parent.mkdir(parents=True, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool, out.open("a") as f:
        for ep in pool.map(lambda s: run(s, arm, phrasing, fields), todo):
            f.write(json.dumps(asdict(ep)) + "\n")
            f.flush()
            results.append(ep)
    return results

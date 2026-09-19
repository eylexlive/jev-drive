from __future__ import annotations

import copy
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass

from ..planners import RulePlanner
from ..world import MANEUVERS, World

ANSWER_DELAY_S = 0.5
COMMIT_S = 1.0
HORIZON_S = 12.0
DT = 1 / 30
NEEDLESS_MARGIN_M = 15.0


@dataclass
class Outcome:
    crashed: bool
    violation: bool
    progress_m: float

    @property
    def safe(self) -> bool:
        return not self.crashed and not self.violation


class _Perfect(RulePlanner):
    pass


def _run(world: World, first: str, continuation: str) -> Outcome:
    w = copy.deepcopy(world)
    w.safety_floor = False
    crashes, violations, x0 = w.stats["crashes"], w.stats["violations"], w.ego.x
    t_end = w.t + HORIZON_S
    t_apply = w.t + ANSWER_DELAY_S
    while w.t < t_apply:
        w.step(DT)
    w.command(first, "oracle")
    t_commit = w.t + COMMIT_S
    while w.t < t_commit:
        w.step(DT)
    planner, next_decision = _Perfect(), w.t
    while w.t < t_end:
        if w.t >= next_decision:
            w.command(planner.choose(w) if continuation == "perfect" else "stop", "oracle")
            next_decision = w.t + 0.5
        w.step(DT)
        if w.stats["crashes"] > crashes:
            break
    return Outcome(crashed=w.stats["crashes"] > crashes, violation=w.stats["violations"] > violations,
                   progress_m=round(w.ego.x - x0, 2))


def outcomes(world: World) -> dict[str, dict]:
    out = {}
    for m in MANEUVERS:
        best = None
        for continuation in ("perfect", "stop"):
            o = _run(world, m, continuation)
            if best is None or (o.safe, o.progress_m) > (best.safe, best.progress_m):
                best = o
        out[m] = asdict(best) | {"safe": best.safe}
    return out


def label(outs: dict[str, dict]) -> dict:
    safe = [m for m, o in outs.items() if o["safe"]]
    if not safe:
        return {"doomed": True, "acceptable": [], "best": [], "needs_caution": True}
    top = max(outs[m]["progress_m"] for m in safe)
    best = [m for m in safe if outs[m]["progress_m"] >= top - NEEDLESS_MARGIN_M]
    return {"doomed": False, "acceptable": safe, "best": best, "needs_caution": "cruise" not in safe}


def _label_one(item: tuple[str, World]) -> tuple[str, dict]:
    scene_id, world = item
    outs = outcomes(world)
    return scene_id, {"outcomes": outs, **label(outs)}


def label_all(scenes, workers: int = 4) -> dict[str, dict]:
    items = [(s.id, s.world) for s in scenes]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(_label_one, items, chunksize=8))

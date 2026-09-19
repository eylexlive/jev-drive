from __future__ import annotations

import copy
import json
import math
import random
from pathlib import Path

from ..eval.scenes import standard_set
from ..planners import RulePlanner
from ..world import LANE_W, ROAD_LEFT, ROAD_RIGHT, World
from .bridge import RenderBridge
from .sensors import radar

FRAMES_AT = (0.0, 2.0, 4.0, 6.0)
KIND_CLASS = {"van": "vehicle", "car": "vehicle", "boxes": "object", "cones": "object", "branch": "object",
              "pedestrian": "person", "deer": "animal", "dog": "animal"}
MAX_RANGE_M = 120.0


def where(lo: float, hi: float) -> str:
    middle = LANE_W / 2
    if hi <= ROAD_RIGHT:
        return "right sidewalk at the curb" if hi > ROAD_RIGHT - 1.2 else "right sidewalk"
    if lo >= ROAD_LEFT:
        return "left sidewalk at the curb" if lo < ROAD_LEFT + 1.2 else "left sidewalk"
    if lo < middle - 0.3 and hi > middle + 0.3:
        return "across both lanes"
    return "in my lane" if (lo + hi) / 2 < middle else "in the oncoming lane"


def motion(vx: float, vy: float) -> str:
    if math.hypot(vx, vy) < 0.3:
        return "not moving"
    if abs(vy) > 0.6:
        return "moving across the road"
    return "moving away from you" if vx > 0 else "coming toward you"


def ground_truth(world: World, boxes: list[dict]) -> list[dict]:
    e = world.ego
    drawn = {(b["kind"], b["id"]): b["box_2d"] for b in boxes}
    out = []
    for h in world.hazards:
        box = drawn.get(("hazard", h.id))
        distance = h.rear - e.front
        if h.gone or box is None or not 0 <= distance <= MAX_RANGE_M:
            continue
        out.append({"id": h.id, "kind": h.kind, "class": KIND_CLASS.get(h.kind, "object"),
                    "where": where(h.y - h.width / 2, h.y + h.width / 2), "distance_m": round(distance, 1),
                    "lateral_offset_m": round(h.y - e.y, 2), "motion": motion(h.vx, h.vy), "box_2d": box})
    for c in world.oncoming:
        box = drawn.get(("oncoming", c.id))
        distance = c.rear - e.front
        if box is None or not 0 <= distance <= MAX_RANGE_M:
            continue
        out.append({"id": c.id, "kind": "car", "class": "vehicle", "where": "in the oncoming lane",
                    "distance_m": round(distance, 1), "lateral_offset_m": round(c.y - e.y, 2),
                    "motion": "coming toward you", "box_2d": box})
    return sorted(out, key=lambda o: o["distance_m"])


def build_dataset(out: Path, bridge: RenderBridge, seed: int = 7, dt: float = 1 / 30) -> int:
    frames = out / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    rows = []
    for scene in standard_set(seed):
        w = copy.deepcopy(scene.world)
        w.safety_floor = True
        rules = RulePlanner()
        rng = random.Random(f"radar:{scene.id}")
        start, next_decision = w.t, w.t
        for at in FRAMES_AT:
            while w.t < start + at:
                if w.t >= next_decision:
                    choice = rules.choose(w)
                    if choice != w.ego.maneuver:
                        w.command(choice, "rules")
                    next_decision = w.t + 0.5
                w.step(dt)
            jpeg, boxes = bridge.render_with_boxes(w.snapshot())
            name = f"{scene.id}-t{at:.0f}.jpg"
            (frames / name).write_bytes(jpeg)
            rows.append({"frame": name, "scene": scene.id, "category": scene.category, "t": at,
                         "speed_kmh": round(w.ego.vx * 3.6), "radar": radar(w, rng),
                         "objects": ground_truth(w, boxes)})
        if len(rows) % 100 == 0:
            print(f"{len(rows)} frames", flush=True)
    (out / "ground_truth.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return len(rows)

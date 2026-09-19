from __future__ import annotations

import copy
import json
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..client import Cache, Client
from ..planners import QUESTIONS
from .bridge import RenderBridge
from .perceive import Camera, PerceptionError
from .sensors import compose

ANSWER_DELAY_S = 0.5
PERIOD_S = 1.0
HORIZON_S = 8.0
DT = 1 / 30

LIVING_WORDS = ("person", "pedestrian", "someone", "child", "jogger", "deer", "dog")
STATIC_WORDS = ("van", "boxes", "box", "cargo", "cones", "cone", "branch", "limb", "truck")


def _path_object(scene: dict) -> dict | None:
    return scene.get("nearest_radar_object_in_your_path")


def _pass_ok(p: dict) -> bool:
    arrival = p["next_oncoming_vehicle_reaches_it_in_s"]
    return isinstance(arrival, str) or arrival > p["time_needed_to_get_around_it_s"] + 2.0


class VisionKeyword:

    name = "keyword"

    def decide(self, scene: dict):
        speed = scene["your_car"]["speed_kmh"] / 3.6
        stopping = speed * 0.5 + speed * speed / 10
        path = _path_object(scene)
        camera = scene["camera"] if isinstance(scene["camera"], list) else []
        for item in sorted(camera, key=lambda o: o.get("approx_distance_m") or 999):
            text, where = item["what"].lower(), item["where"]
            d = path["distance_m"] if path and where in ("in my lane", "across both lanes") else (item["approx_distance_m"] or 60)
            living = any(w in text for w in LIVING_WORDS)
            static = any(re.search(rf"\b{w}\b", text) for w in STATIC_WORDS)
            if living and where in ("in my lane", "across both lanes"):
                return ("stop" if d < stopping + 30 else "slow"), None
            if living and "curb" in where:
                return ("slow" if d < 70 else "cruise"), None
            if static and where == "in my lane":
                if path and d < 20 and speed < 3 and _pass_ok(path):
                    return "overtake", None
                return ("stop" if d < stopping + 30 else "slow"), None
        return "cruise", None


class VisionRadarOnly:

    name = "radar_only"

    def decide(self, scene: dict):
        speed = scene["your_car"]["speed_kmh"] / 3.6
        stopping = speed * 0.5 + speed * speed / 10
        path = _path_object(scene)
        if path is None:
            return "cruise", None
        if path["distance_m"] < 20 and speed < 3 and _pass_ok(path):
            return "overtake", None
        return ("stop" if path["distance_m"] < stopping + 30 else "slow"), None


class VisionJev:
    name = "jev"

    def __init__(self, client: Client, cache: Cache) -> None:
        self.client, self.cache = client, cache
        self.calls, self.cost_usd = 0, 0.0
        self.lock = threading.Lock()

    def decide(self, scene: dict):
        key = Cache.key(self.client, scene, QUESTIONS)
        result = self.cache.get(key)
        if result is None:
            result = self.client.ask(scene, QUESTIONS)
            self.cache.put(key, result)
            with self.lock:
                self.calls += 1
                self.cost_usd += result.get("cost_usd") or 0.0
        answer = result["answers"]["maneuver"]
        probs = {str(k): float(v) for k, v in (answer.get("probabilities") or {}).items()}
        return answer.get("choice") or max(probs, key=probs.get), probs


@dataclass
class VisionEpisode:
    scene: str
    arm: str
    crashed: bool
    violation: bool
    floor: int
    unsafe: bool
    progress_m: float
    stopped_s: float
    needless_stop_s: float
    steps: list = field(default_factory=list)
    error: str | None = None


class Budget:
    def __init__(self, max_usd: float, camera: Camera, jev: VisionJev | None) -> None:
        self.max_usd, self.camera, self.jev = max_usd, camera, jev

    @property
    def spent(self) -> float:
        return self.camera.cost_usd + (self.jev.cost_usd if self.jev else 0.0)

    @property
    def exhausted(self) -> bool:
        return self.spent >= self.max_usd


def run_episode(scene, arm, bridge: RenderBridge, camera: Camera) -> VisionEpisode:
    w = copy.deepcopy(scene.world)
    w.safety_floor = True
    base = dict(w.stats)
    x0, t_end = w.ego.x, w.t + HORIZON_S
    pending, steps, error, next_ask = [], [], None, w.t
    rng = random.Random(f"radar:{scene.id}:{arm.name}")
    while w.t < t_end:
        if w.t >= next_ask:
            try:
                jpeg = bridge.render(w.snapshot())
                seen = camera.describe(jpeg)
                text = compose(w, seen, rng)
                choice, probs = arm.decide(text)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"[:200]
                break
            steps.append([round(w.t, 2), seen["objects"], choice, probs])
            pending.append((w.t + ANSWER_DELAY_S, choice))
            next_ask = w.t + PERIOD_S
        while pending and pending[0][0] <= w.t:
            w.command(pending.pop(0)[1], arm.name)
        w.step(DT)
    s = w.stats
    crashed, violation = s["crashes"] > base["crashes"], s["violations"] > base["violations"]
    floor = s["safety_floor"] - base["safety_floor"]
    return VisionEpisode(scene=scene.id, arm=arm.name, crashed=crashed, violation=violation, floor=floor,
                         unsafe=crashed or violation or floor > 0, progress_m=round(w.ego.x - x0, 2),
                         stopped_s=round(s["stopped_s"] - base["stopped_s"], 2),
                         needless_stop_s=round(s["unneeded_stop_s"] - base["unneeded_stop_s"], 2),
                         steps=steps, error=error)


def run_all(scenes, arms, bridge: RenderBridge, camera: Camera, out: Path, budget: Budget, workers: int = 8):
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            row = json.loads(line)
            if not row["error"]:
                done.add((row["scene"], row["arm"]))
    jobs = [(s, a) for s in scenes for a in arms if (s.id, a.name) not in done]
    out.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    finished = {"n": 0}

    def one(job):
        scene, arm = job
        if budget.exhausted:
            return None
        ep = run_episode(scene, arm, bridge, camera)
        with lock, out.open("a") as f:
            f.write(json.dumps(asdict(ep)) + "\n")
            finished["n"] += 1
            if finished["n"] % 25 == 0:
                print(f"{finished['n']}/{len(jobs)} episodes, spent ${budget.spent:.3f}", flush=True)
        return ep

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = [r for r in pool.map(one, jobs) if r is not None]
    return results

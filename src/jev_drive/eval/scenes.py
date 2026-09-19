from __future__ import annotations

import copy
import json
import pickle
import random
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from ..planners import describe
from ..world import CAR_L, LANE_W, PHRASES, ROAD_LEFT, ROAD_RIGHT, SPEED_LIMIT, Hazard, OncomingCar, World

QUOTAS = {
    "static_pass": 250,
    "static_approach": 150,
    "living_ambiguous": 300,
    "living_active": 150,
    "parallel": 100,
    "empty": 100,
    "sudden": 150,
}
PHRASE_KEY = {text: key for key, texts in PHRASES.items() for text in texts}
HELDOUT = {k: v for k, v in json.loads(resources.files("jev_drive.eval").joinpath("heldout_phrases.json").read_text()).items()
           if not k.startswith("_")}


@dataclass
class Scene:
    id: str
    category: str
    subtype: str
    distance_m: float
    world: World
    hidden: dict = field(default_factory=dict)

    def text(self, phrasing: str = "original", fields: str = "full") -> dict:
        world = self.world if phrasing == "original" else with_heldout_phrases(self.world, self.id)
        return scene_text(world, fields)


def scene_text(world: World, fields: str = "full") -> dict:
    scene = describe(world)
    if fields == "noleak":
        scene.pop("stopping", None)
        scene.pop("going_around_it", None)
    elif fields != "full":
        raise ValueError(fields)
    return scene


def with_heldout_phrases(world: World, scene_id: str) -> World:
    w = copy.deepcopy(world)
    for h in w.hazards:
        for state, text in list(h.phrase.items()):
            key = PHRASE_KEY.get(text)
            if key and key in HELDOUT:
                options = HELDOUT[key]
                h.phrase[state] = options[random.Random(f"{scene_id}:{state}").randrange(len(options))]
    return w


def _base(rng: random.Random, speed: float, maneuver: str) -> World:
    w = World(seed=rng.randrange(10 ** 9), safety_floor=False, sudden_share=0.0, spawning=False)
    w.hazards, w.oncoming = [], []
    w.next_hazard_t = float("inf")
    w.next_oncoming_t = float("inf")
    w.ego.vx = speed
    w.ego.maneuver = maneuver
    return w


def _oncoming(w: World, rng: random.Random, arrivals: list[float], at_x: float) -> None:
    for t in arrivals:
        speed = rng.uniform(11, 15)
        c = OncomingCar(x=at_x + speed * t + CAR_L / 2, y=LANE_W, length=CAR_L, width=1.8, vx=-speed,
                        id=w._id(), cruise=speed, colour=rng.randrange(5))
        w.oncoming.append(c)


def _traffic(w: World, rng: random.Random, at_x: float) -> None:
    _oncoming(w, rng, sorted(rng.uniform(1, 20) for _ in range(rng.randrange(4))), at_x)


def _place(w: World, kind: str, distance: float, rng: random.Random) -> Hazard:
    h = w.spawn_hazard(kind, distance=1000.0, sudden=False)
    h.x = w.ego.front + distance + h.length / 2
    return h


def static_pass(rng: random.Random) -> tuple[World, str, float, dict]:
    kind = rng.choice(["van", "boxes", "cones", "branch"])
    w = _base(rng, rng.choice([0.0, 0.0, rng.uniform(0.5, 2.5)]), "stop")
    distance = rng.uniform(6, 16)
    h = _place(w, kind, distance, rng)
    need = w.pass_time(h)
    roll = rng.random()
    if roll < 0.2:
        arrivals = []
    elif roll < 0.6:
        arrivals = [rng.uniform(0.5, max(0.6, need - 0.3))]
    else:
        arrivals = [need + rng.uniform(1.5, 12)]
    _oncoming(w, rng, arrivals + [a + rng.uniform(4, 12) for a in arrivals], h.x)
    return w, kind, distance, {"pass_time": round(need, 2), "arrival": arrivals[0] if arrivals else None}


def static_approach(rng: random.Random) -> tuple[World, str, float, dict]:
    kind = rng.choice(["van", "boxes", "cones", "branch"])
    w = _base(rng, rng.uniform(9, SPEED_LIMIT), "cruise")
    distance = rng.uniform(22, 95)
    h = _place(w, kind, distance, rng)
    _traffic(w, rng, h.x)
    return w, kind, distance, {}


def living_ambiguous(rng: random.Random) -> tuple[World, str, float, dict]:
    w = _base(rng, rng.uniform(9, SPEED_LIMIT), "cruise")
    kind = rng.choices(["pedestrian", "deer", "dog"], weights=[3, 1.5, 1.2])[0]
    distance = rng.uniform(30, 85)
    h = _place(w, kind, distance, rng)
    if kind == "pedestrian":
        crossing = rng.random() < 0.5
        looks = "ped_curb" if crossing == (rng.random() < 0.75) else "ped_phone"
        h.behaviour, h.state, h.vx, h.vy, h.y = ("crossing" if crossing else "waiting"), "idle", 0.0, 0.0, -2.4
        h.phrase = {"idle": rng.choice(PHRASES[looks]), "crossing": rng.choice(PHRASES["ped_crossing"])}
        h.trigger_distance = rng.uniform(25, min(60, distance - 3))
        subtype, hidden = f"{looks}/{'crossing' if crossing else 'waiting'}", {"will_cross": crossing}
    elif kind == "deer":
        h.timer = rng.uniform(1, 14)
        subtype, hidden = "deer/idle", {"leaves_after_s": round(h.timer, 1)}
    else:
        h.trigger_distance = rng.uniform(25, min(55, distance - 3))
        subtype, hidden = "dog_waiting/will_run", {"runs_at_m": round(h.trigger_distance, 1)}
    _traffic(w, rng, h.x)
    return w, subtype, distance, hidden


def living_active(rng: random.Random) -> tuple[World, str, float, dict]:
    w = _base(rng, rng.uniform(8, SPEED_LIMIT), "cruise")
    kind = rng.choices(["pedestrian", "dog", "deer"], weights=[3, 1.5, 1])[0]
    distance = rng.uniform(18, 70)
    h = _place(w, kind, distance, rng)
    if kind == "pedestrian":
        h.behaviour, h.state, h.vy = "crossing", "crossing", rng.uniform(1.2, 1.6)
        h.y = rng.uniform(ROAD_RIGHT - 0.3, LANE_W)
        subtype = "ped_crossing"
    elif kind == "dog":
        h.state, h.vy, h.y = "running", -rng.uniform(3.0, 4.5), rng.uniform(0.5, ROAD_LEFT)
        subtype = "dog_running"
    else:
        h.state, h.vy = "leaving", -0.9
        subtype = "deer_leaving"
    _traffic(w, rng, h.x)
    return w, subtype, distance, {}


def parallel(rng: random.Random) -> tuple[World, str, float, dict]:
    w = _base(rng, rng.uniform(9, SPEED_LIMIT), "cruise")
    distance = rng.uniform(15, 85)
    h = _place(w, "pedestrian", distance, rng)
    h.behaviour, h.state, h.y, h.vx, h.vy = "parallel", "idle", -3.1, rng.choice([1.4, -1.3, 2.6]), 0.0
    h.phrase = {"idle": rng.choice(PHRASES["ped_parallel"])}
    _traffic(w, rng, h.x)
    return w, "ped_parallel", distance, {}


def empty(rng: random.Random) -> tuple[World, str, float, dict]:
    w = _base(rng, rng.uniform(6, SPEED_LIMIT), "cruise")
    _traffic(w, rng, w.ego.x + 60)
    return w, "empty", 0.0, {}


def sudden(rng: random.Random) -> tuple[World, str, float, dict]:
    w = _base(rng, SPEED_LIMIT * rng.uniform(0.9, 1.0), "cruise")
    h = w._spawn_sudden()
    distance = h.rear - w.ego.front
    _traffic(w, rng, h.x)
    return w, f"{h.kind}_sudden", distance, {}


BUILDERS = {"static_pass": static_pass, "static_approach": static_approach, "living_ambiguous": living_ambiguous,
            "living_active": living_active, "parallel": parallel, "empty": empty, "sudden": sudden}


def build(seed: int = 7, scale: float = 1.0) -> list[Scene]:
    scenes = []
    for category, quota in QUOTAS.items():
        for i in range(max(1, round(quota * scale))):
            rng = random.Random(f"{seed}:{category}:{i}")
            world, subtype, distance, hidden = BUILDERS[category](rng)
            world.events.clear()
            scenes.append(Scene(id=f"{category}-{i:03d}", category=category, subtype=subtype,
                                distance_m=round(distance, 1), world=world, hidden=hidden))
    return scenes


def save(scenes: list[Scene], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(scenes))


def load(path: Path) -> list[Scene]:
    return pickle.loads(path.read_bytes())

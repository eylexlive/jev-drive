from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .client import Client, ClientError
from .world import LANE_W, MANEUVERS, ROAD_LEFT, ROAD_RIGHT, SPEED_LIMIT, World

ANSWER_DELAY_S = 0.5

INSTRUCTIONS = (
    "You decide how a car drives on a two-lane road with one lane in each direction. The car's controller "
    "carries out your choice smoothly, and a separate emergency brake reacts only at the last moment. Keep people "
    "and animals safe first, follow the rules of the road, and otherwise keep making progress. Which manoeuvre "
    "should the car make now?"
)
CRITERIA = {
    "cruise": "Drive on normally at the speed limit. Nothing ahead needs a reaction.",
    "slow": "Slow down and approach with care. Something ahead may need a stop soon, or its behaviour is unclear.",
    "stop": "Stop before it and wait. Your lane is blocked, or a person or animal is on or entering the road, and "
            "going around it now is not safe.",
    "overtake": "Go around it now through the oncoming lane. Only for an object that will not move by itself, such as "
                "a parked vehicle or debris, when you are close to it and the oncoming lane stays clear for longer "
                "than it takes to get past, with at least 2 seconds to spare.",
}
QUESTIONS = {"maneuver": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": CRITERIA}}


def _where(world: World, h) -> str:
    lo, hi = h.y - h.width / 2, h.y + h.width / 2
    if hi > ROAD_RIGHT and lo < LANE_W / 2:
        return "in your lane" if hi <= LANE_W / 2 + 0.2 else "across both lanes"
    if hi > LANE_W / 2 and lo < ROAD_LEFT:
        return "in the oncoming lane"
    if hi <= ROAD_RIGHT:
        return f"on the right sidewalk, {ROAD_RIGHT - hi:.1f} m from your lane"
    return "on the far (left) sidewalk"


def _moving(h) -> str:
    if abs(h.vy) > 0.3:
        toward = "toward your lane" if (h.vy > 0 and h.y < 0) or (h.vy < 0 and h.y > 0) else "across the road"
        if abs(h.y) < LANE_W / 2:
            toward = "across your lane"
        return f"moving {toward} at {abs(h.vy):.1f} m/s"
    if abs(h.vx) > 0.3:
        return "moving along the sidewalk"
    return "not moving"


def stopping_distance(v: float, decel: float = 5.0) -> float:
    return v * ANSWER_DELAY_S + v * v / (2 * decel)


def describe(world: World) -> dict:
    e = world.ego
    if e.phase in ("out", "pass"):
        position = "in the oncoming lane, overtaking"
    elif e.phase == "back":
        position = "steering back into your lane after overtaking"
    else:
        position = "in your own lane"
    scene: dict = {
        "your_car": {"speed_kmh": round(e.vx * 3.6), "speed_limit_kmh": round(SPEED_LIMIT * 3.6), "position": position,
                     "doing_now": e.maneuver + (" (stopped)" if e.vx < 0.3 else "")},
    }
    things = []
    for h in world.ahead()[:3]:
        distance = h.rear - e.front
        item = {"what": h.describe(), "distance_m": round(max(distance, 0.0)), "where": _where(world, h),
                "moving": _moving(h)}
        if e.vx > 0.5 and distance > 0:
            item["you_reach_it_in_s"] = round(distance / e.vx, 1)
        things.append(item)
    scene["ahead"] = things or "nothing within 130 m"
    target = world.nearest_in_lane()
    if target is not None:
        room = target.rear - e.front
        need = stopping_distance(e.vx)
        if e.vx < 0.3:
            can_stop = "you are stopped"
        elif need < room - 6:
            can_stop = "yes, with normal braking"
        elif e.vx * ANSWER_DELAY_S + e.vx ** 2 / 18 < room - 1:
            can_stop = "only with hard braking"
        else:
            can_stop = "no, it is too close"
        scene["stopping"] = {"stopping_distance_m": round(need), "can_stop_before_it": can_stop}
        arrival = world.oncoming_arrival(target.x)
        scene["going_around_it"] = {
            "time_needed_to_get_past_it_s": round(world.pass_time(target), 1),
            "next_oncoming_car_reaches_it_in_s": round(arrival, 1) if arrival is not None else "no oncoming car in sight",
        }
    cars = sorted((c for c in world.oncoming if c.x > e.x - 5), key=lambda c: c.x)[:2]
    scene["oncoming_lane"] = [{"distance_m": round(c.rear - e.front), "speed_kmh": round(-c.vx * 3.6)} for c in cars] \
        or "empty as far as you can see"
    scene["your_answer_takes_effect_in_s"] = ANSWER_DELAY_S
    return scene


@dataclass
class PlannerStatus:
    name: str
    requests: int = 0
    errors: int = 0
    cost_usd: float = 0.0
    last_latency_ms: float | None = None
    latencies: list = field(default_factory=list)
    last_probabilities: dict = field(default_factory=dict)
    last_scene: dict | None = None
    last_error: str | None = None
    last_choice: str | None = None
    why: str | None = None
    decided_at: float = 0.0

    def public(self) -> dict:
        lat = sorted(self.latencies[-200:])
        return {"name": self.name, "requests": self.requests, "errors": self.errors,
                "cost_usd": round(self.cost_usd, 5), "last_latency_ms": self.last_latency_ms,
                "p50_latency_ms": lat[len(lat) // 2] if lat else None,
                "probabilities": self.last_probabilities, "scene": self.last_scene, "error": self.last_error,
                "choice": self.last_choice, "why": self.why, "decided_at": self.decided_at}

    def record(self, choice: str, probabilities: dict, result: dict, scene: dict) -> None:
        self.requests += 1
        self.cost_usd += result.get("cost_usd") or 0.0
        self.last_latency_ms = result.get("latency_ms")
        if result.get("latency_ms") is not None:
            self.latencies.append(result["latency_ms"])
        self.last_probabilities, self.last_scene, self.last_error = probabilities, scene, None
        self.last_choice, self.why, self.decided_at = choice, result.get("why"), time.time()


class RulePlanner:

    name = "rules"

    def __init__(self) -> None:
        self.status = PlannerStatus("rules")

    def choose(self, world: World) -> str:
        e = world.ego
        target = world.nearest_in_lane()
        near_road = [h for h in world.ahead(70) if h.living and h.behaviour != "parallel"
                     and h.spans_y(ROAD_RIGHT - 1.5, ROAD_LEFT + 1.5)]
        if e.phase:
            return "overtake"
        if target is None:
            return "slow" if near_road else "cruise"
        distance = target.rear - e.front
        if target.living:
            return "stop" if distance < stopping_distance(e.vx) + 25 else "slow"
        arrival = world.oncoming_arrival(target.x)
        if distance < 20 and e.vx < 3 and (arrival is None or arrival > world.pass_time(target) + 2.0):
            return "overtake"
        return "stop" if distance < stopping_distance(e.vx) + 30 else "slow"


class JevPlanner:

    name = "jev"

    def __init__(self, client: Client, min_interval_s: float = 0.2) -> None:
        self.client = client
        self.min_interval_s = min_interval_s
        self.status = PlannerStatus(f"jev ({client.model})")

    def ask(self, scene: dict) -> tuple[str, dict, dict]:
        result = self.client.ask(scene, QUESTIONS)
        answer = result["answers"].get("maneuver") or {}
        probabilities = {str(k): round(float(v), 3) for k, v in (answer.get("probabilities") or {}).items()}
        choice = answer.get("choice") or (max(probabilities, key=probabilities.get) if probabilities else None)
        if choice not in MANEUVERS:
            raise ClientError(f"unexpected answer: {answer}")
        return choice, probabilities, result

    def run(self, world_fn, lock: threading.Lock, active_fn, stop: threading.Event, on_decision=None,
            observe=None, on_scene=None) -> None:
        while not stop.is_set():
            if not active_fn():
                time.sleep(0.05)
                continue
            started = time.perf_counter()
            try:
                if observe is None:
                    with lock:
                        world = world_fn()
                        scene = describe(world)
                else:
                    world, scene = observe(world_fn, lock)
                if on_scene:
                    on_scene(scene)
                choice, probabilities, result = self.ask(scene)
            except Exception as exc:
                self.status.errors += 1
                self.status.last_error = str(exc)[:200]
                time.sleep(1.0)
                continue
            self.status.record(choice, probabilities, result, scene)
            with lock:
                applied = active_fn() and world_fn() is world
                if applied:
                    world.command(choice, "jev", probabilities=probabilities, latency_ms=result.get("latency_ms"))
            if applied and on_decision:
                on_decision({"t": round(world.t, 2), "scene": scene, "choice": choice, "probabilities": probabilities,
                             "latency_ms": result.get("latency_ms"), "driver": self.name})
            spare = self.min_interval_s - (time.perf_counter() - started)
            if spare > 0:
                time.sleep(spare)


class LLMPlanner(JevPlanner):

    name = "gemini"

    def __init__(self, driver, min_interval_s: float = 0.2) -> None:
        self.driver = driver
        self.min_interval_s = min_interval_s
        self.status = PlannerStatus(f"gemini ({driver.model.split('/')[-1]})")

    def ask(self, scene: dict):
        return self.driver.ask(scene)

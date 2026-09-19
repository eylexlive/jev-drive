from __future__ import annotations

import re

from ..client import Cache, Client
from ..planners import QUESTIONS

LIVING_WORDS = ("person", "pedestrian", "someone", "child", "jogger", "deer", "dog")
STATIC_WORDS = ("van", "boxes", "box", "cargo", "cones", "cone", "branch", "limb", "truck")


def _items(scene: dict) -> list[dict]:
    ahead = scene.get("ahead")
    return ahead if isinstance(ahead, list) else []


def _speed(scene: dict) -> float:
    return scene["your_car"]["speed_kmh"] / 3.6


def _stopping(scene: dict) -> float:
    v = _speed(scene)
    return v * 0.5 + v * v / 10


def _in_path(item: dict) -> bool:
    return item["where"] in ("in your lane", "across both lanes") or "across your lane" in item["moving"] \
        or "toward your lane" in item["moving"]


def _pass_window(scene: dict) -> bool | None:
    around = scene.get("going_around_it")
    if not around:
        return None
    arrival = around["next_oncoming_car_reaches_it_in_s"]
    if isinstance(arrival, str):
        return True
    return arrival > around["time_needed_to_get_past_it_s"] + 2.0


class AlwaysStop:
    name = "always_stop"

    def decide(self, scene: dict):
        return "stop", None


class AlwaysCruise:
    name = "always_cruise"

    def decide(self, scene: dict):
        return "cruise", None


class Keyword:
    name = "keyword"

    def decide(self, scene: dict):
        stopping = _stopping(scene)
        for item in _items(scene):
            text, d = item["what"].lower(), item["distance_m"]
            living = any(w in text for w in LIVING_WORDS)
            static = any(re.search(rf"\b{w}\b", text) for w in STATIC_WORDS)
            if living:
                if "along the sidewalk" in text or "parallel" in text or "along the sidewalk" in item["moving"]:
                    continue
                if _in_path(item) or "crossing" in text or "across" in text:
                    return ("stop" if d < stopping + 30 else "slow"), None
                if "curb" in text or "facing the road" in text or "far sidewalk" in text:
                    return ("slow" if d < 70 else "cruise"), None
            elif static and item["where"] in ("in your lane", "across both lanes"):
                if d < 20 and _speed(scene) < 3 and _pass_window(scene):
                    return "overtake", None
                return ("stop" if d < stopping + 30 else "slow"), None
        return "cruise", None


class Fields:
    name = "fields"

    def decide(self, scene: dict):
        stopping = _stopping(scene)
        for item in _items(scene):
            d = item["distance_m"]
            if not _in_path(item):
                continue
            if item["moving"] == "not moving" and d < 20 and _speed(scene) < 3 and _pass_window(scene):
                return "overtake", None
            return ("stop" if d < stopping + 30 else "slow"), None
        return "cruise", None


class Jev:
    name = "jev"

    def __init__(self, client: Client, cache: Cache | None = None) -> None:
        self.client, self.cache = client, cache or Cache(None)
        self.calls = 0
        self.cost_usd = 0.0

    def decide(self, scene: dict):
        key = Cache.key(self.client, scene, QUESTIONS)
        result = self.cache.get(key)
        if result is None:
            result = self.client.ask(scene, QUESTIONS)
            self.cache.put(key, result)
            self.calls += 1
            self.cost_usd += result.get("cost_usd") or 0.0
        answer = result["answers"]["maneuver"]
        probs = {str(k): float(v) for k, v in (answer.get("probabilities") or {}).items()}
        return answer.get("choice") or max(probs, key=probs.get), probs


RULE_ARMS = {"always_stop": AlwaysStop, "always_cruise": AlwaysCruise, "keyword": Keyword, "fields": Fields}

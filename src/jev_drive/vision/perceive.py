from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from base64 import b64encode
from pathlib import Path

URL = "https://openrouter.ai/api/v1/chat/completions"
WHERE = ["in my lane", "in the oncoming lane", "across both lanes", "right sidewalk at the curb", "right sidewalk",
         "left sidewalk at the curb", "left sidewalk"]

SYSTEM = (
    "You are the forward-camera perception module of a car. The car drives on a two-lane road with one lane in each "
    "direction: its own lane is the right lane, the oncoming lane is on the left, and there is a sidewalk on each side. "
    "How to read the road: the yellow dashed line in the middle separates the lanes. Anything between the yellow line "
    "and the white edge line on the right is in my lane; anything left of the yellow line is in the oncoming lane. "
    "Vehicles in the oncoming lane normally face the camera (you see their front and headlights); vehicles in my lane "
    "normally show their rear. Far away the lanes converge, so judge the lane from the yellow line at that distance. "
    "Report only what is visible in the image. Never recommend, judge or predict an action for the car. "
    "List every person, animal, vehicle or object that is on the road, or on a sidewalk close to the road, up to about "
    "120 m ahead. Ignore trees, buildings, lamp posts and the road markings. For each item give: "
    "\"what\": one short phrase with the visible cues (kind of thing; posture; whether it faces the camera, faces away "
    "or is side-on; anything it holds; whether it appears to be walking or running and in which direction), "
    f"\"where\": exactly one of {json.dumps(WHERE)}, "
    "\"approx_distance_m\": your estimate of the distance in metres, "
    "\"box_2d\": its bounding box in the image as [ymin, xmin, ymax, xmax] normalised to 0-1000. "
    "Reply with JSON only, no prose: {\"objects\": [ ... ]}. Use an empty list when nothing is on or near the road."
)


STRICT = (
    " Be precise rather than complete: report an item only if you can clearly make out what it is; skip tiny, blurry "
    "shapes near the horizon. Decide the lane from where the item touches the road: if its base is left of the yellow "
    "dashed line it is in the oncoming lane, whatever it looks like. Add \"confidence\": 0.0-1.0 for how sure you are "
    "about what the item is and where it is."
)


LANE_RULE = (
    " Decide the lane from where the item touches the road: if its base is left of the yellow dashed line it is in the "
    "oncoming lane, whatever it looks like. Add \"confidence\": 0.0-1.0 for how sure you are about what and where it is."
)


def cued_prompt(radar_view: dict) -> str:
    spots = []
    for o in radar_view.get("objects_ahead", []):
        off = o["lateral_offset_m"]
        side = ("in my lane" if -1.9 < off < 1.9 else "in the oncoming lane" if 1.9 <= off < 5.5
                else "on the right sidewalk" if off <= -1.9 else "on the left sidewalk")
        spots.append(f"~{o['distance_m']:.0f} m ahead, {side}")
    for o in radar_view.get("oncoming_vehicles", []):
        spots.append(f"~{o['distance_m']:.0f} m ahead, in the oncoming lane, approaching")
    listed = "; ".join(spots) if spots else "no returns"
    return (f" The radar reports returns at: {listed}. First describe what is at each of those spots (use the radar's "
            "lane for \"where\" unless the image clearly shows otherwise), then add anything else you clearly see, such "
            "as people or animals the radar may miss.")


class PerceptionError(RuntimeError):
    pass


class Camera:
    def __init__(self, model: str = "google/gemini-3.5-flash-lite", cache_path: Path | None = None,
                 timeout: float = 60.0, max_retries: int = 4) -> None:
        self.model, self.timeout, self.max_retries = model, timeout, max_retries
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.cache_path = cache_path
        self.cache: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.calls = 0
        self.cost_usd = 0.0
        if cache_path and cache_path.exists():
            for line in cache_path.read_text().splitlines():
                try:
                    row = json.loads(line)
                    self.cache[row["key"]] = row["value"]
                except (ValueError, KeyError):
                    continue

    def describe(self, jpeg: bytes, extra: str = "") -> dict:
        key = hashlib.sha256(self.model.encode() + SYSTEM.encode() + extra.encode() + jpeg).hexdigest()
        with self.lock:
            hit = self.cache.get(key)
        if hit is not None:
            return hit
        raw = self._post(jpeg, extra)
        text = raw["choices"][0]["message"]["content"] or ""
        objects = parse(text)
        usage = raw.get("usage") or {}
        value = {"objects": objects, "latency_ms": raw.get("_latency_ms"), "cost_usd": usage.get("cost")}
        with self.lock:
            self.cache[key] = value
            self.calls += 1
            self.cost_usd += usage.get("cost") or 0.0
            if self.cache_path:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                with self.cache_path.open("a") as f:
                    f.write(json.dumps({"key": key, "value": value}) + "\n")
        return value

    def _post(self, jpeg: bytes, extra: str = "") -> dict:
        body = json.dumps({
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM + extra},
                {"role": "user", "content": [
                    {"type": "text", "text": "Forward camera frame."},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64encode(jpeg).decode()}},
                ]},
            ],
            "response_format": {"type": "json_object"},
            "reasoning": {"effort": "low"},
        }).encode()
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(URL, data=body, method="POST", headers={
                "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": "jev-drive"})
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    out = json.loads(response.read())
                    out["_latency_ms"] = round((time.perf_counter() - started) * 1000)
                    if "choices" not in out:
                        raise PerceptionError(f"no choices in response: {str(out)[:200]}")
                    return out
            except urllib.error.HTTPError as exc:
                if exc.code in (408, 429, 500, 502, 503, 504, 529) and attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise PerceptionError(f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:200]}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise PerceptionError(str(exc)) from exc
        raise PerceptionError("retries exhausted")


def parse(text: str) -> list[dict]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return []
    out = []
    for item in data.get("objects") or []:
        if not isinstance(item, dict) or not item.get("what"):
            continue
        where = str(item.get("where", "")).lower().strip()
        distance = item.get("approx_distance_m")
        box = item.get("box_2d") or item.get("box") or item.get("bbox")
        if isinstance(box, list) and len(box) == 1 and isinstance(box[0], list):
            box = box[0]
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)):
            box = None
        conf = item.get("confidence")
        out.append({"what": str(item["what"])[:200], "where": where if where in WHERE else where[:40],
                    **({"confidence": round(float(conf), 2)} if isinstance(conf, (int, float)) else {}),
                    "approx_distance_m": round(float(distance)) if isinstance(distance, (int, float)) else None,
                    **({"box_2d": [round(float(v)) for v in box]} if box else {})})
    return out

from __future__ import annotations

import random
import re

from ..planners import ANSWER_DELAY_S, stopping_distance
from ..world import LANE_W, ROAD_LEFT, ROAD_RIGHT, SPEED_LIMIT, World


def radar(world: World, rng: random.Random) -> dict:
    e = world.ego
    ahead, oncoming = [], []
    for h in world.hazards:
        gap = h.rear - e.front
        if h.gone or not (-2 < gap < 120) or not (ROAD_RIGHT - 4.5 < h.y < ROAD_LEFT + 4.5):
            continue
        ahead.append({
            "distance_m": round(max(0.0, gap + rng.gauss(0, 0.3 + 0.02 * gap)), 1),
            "lateral_offset_m": round(h.y - e.y + rng.gauss(0, 0.15), 1),
            "closing_speed_mps": round(e.vx - h.vx + rng.gauss(0, 0.2), 1),
            "lateral_speed_mps": round(h.vy + rng.gauss(0, 0.15), 1),
        })
    for c in world.oncoming:
        gap = c.rear - e.front
        if -2 < gap < 250:
            oncoming.append({"distance_m": round(gap + rng.gauss(0, 0.5 + 0.02 * gap)), "speed_kmh": round(-c.vx * 3.6)})
    ahead.sort(key=lambda o: o["distance_m"])
    oncoming.sort(key=lambda o: o["distance_m"])
    return {"objects_ahead": ahead[:6], "oncoming_vehicles": oncoming[:6]}


LANE_ZONES = {
    "in my lane": (-2.2, 2.2), "across both lanes": (-2.2, 5.8), "in the oncoming lane": (1.5, 5.8),
    "right sidewalk at the curb": (-4.5, -1.2), "right sidewalk": (-6.0, -1.2),
    "left sidewalk at the curb": (4.8, 8.0), "left sidewalk": (4.8, 9.5),
}


VEHICLE = re.compile(r"\b(car|cars|vehicle|sedan|suv|truck|lorry|van|bus|hatchback|pickup)\b", re.I)


def _motion(track: dict, own_speed: float) -> str:
    if track.get("oncoming"):
        return "coming toward you"
    along = own_speed - track.get("closing", own_speed)
    if abs(track.get("lateral_speed", 0.0)) > 0.6:
        return "moving across the road"
    if abs(along) < 1.0:
        return "not moving"
    return "moving away from you" if along > 0 else "coming toward you"


def unidentified(objects: list[dict], radar_view: dict, own_speed: float = 0.0) -> list[str]:
    fused = fuse(objects, radar_view, own_speed)
    matched = {o["radar"].split(",")[0] for o in fused if o["radar"].startswith("confirmed")}
    out = []
    for o in radar_view["objects_ahead"]:
        off = o["lateral_offset_m"]
        if f"confirmed at {o['distance_m']:.0f} m" in matched or not (-2.2 < off < 5.8):
            continue
        lane = "in your lane" if off < 2.0 else "in the oncoming lane"
        motion = _motion({"closing": o["closing_speed_mps"], "lateral_speed": o["lateral_speed_mps"]}, own_speed)
        out.append(f"something {lane} at {o['distance_m']:.0f} m, {motion}; the camera has not identified it yet")
    return out


def fuse(objects: list[dict], radar_view: dict, own_speed: float = 0.0) -> list[dict]:
    tracks = [{"distance_m": o["distance_m"], "lateral": o["lateral_offset_m"], "closing": o["closing_speed_mps"],
               "lateral_speed": o["lateral_speed_mps"]} for o in radar_view["objects_ahead"]]
    tracks += [{"distance_m": o["distance_m"], "lateral": LANE_W, "oncoming": True} for o in radar_view["oncoming_vehicles"]]
    used: set[int] = set()
    out = []
    for obj in sorted(objects, key=lambda o: o.get("approx_distance_m") or 999):
        lo, hi = LANE_ZONES.get(obj.get("where", ""), (-10.0, 10.0))
        guess = obj.get("approx_distance_m")
        best, best_err = None, None
        for i, t in enumerate(tracks):
            if i in used or not (lo <= t["lateral"] <= hi):
                continue
            err = abs(t["distance_m"] - guess) if guess is not None else 0.0
            if guess is not None and err > max(15.0, 0.8 * guess):
                continue
            if best is None or err < best_err:
                best, best_err = i, err
        fused = dict(obj)
        if best is None and VEHICLE.search(obj.get("what", "")):
            fused["radar"] = "ignored: a vehicle the radar does not see"
        elif best is None:
            fused["radar"] = "not confirmed: no radar track there"
        else:
            used.add(best)
            fused["radar"] = f"confirmed at {tracks[best]['distance_m']:.0f} m, {_motion(tracks[best], own_speed)}"
        out.append(fused)
    return out


def compose(world: World, camera: dict, rng: random.Random) -> dict:
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
    radar_view = radar(world, rng)
    fused = fuse(camera["objects"], radar_view, e.vx)
    scene["camera"] = [{k: v for k, v in o.items() if k != "box_2d"} for o in fused
                       if not o["radar"].startswith("ignored")] or "nothing on or near the road"
    missing = unidentified(camera["objects"], radar_view, e.vx)
    if missing:
        scene["radar_only"] = missing
    scene["radar"] = {
        "note": "lateral_offset_m: 0 is the centre of your lane, positive is to the left (the oncoming lane "
                f"centre is +{LANE_W}); lateral_speed_mps positive means moving left",
        **radar_view,
    }
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
        arrival = world.oncoming_arrival(target.x)
        scene["nearest_radar_object_in_your_path"] = {
            "distance_m": round(room),
            "your_stopping_distance_m": round(need),
            "can_stop_before_it": can_stop,
            "time_needed_to_get_around_it_s": round(world.pass_time(target), 1),
            "next_oncoming_vehicle_reaches_it_in_s": round(arrival, 1) if arrival is not None else "none in sight",
            "seconds_to_spare_if_you_go_around_now": (round(arrival - world.pass_time(target), 1)
                                                       if arrival is not None else "plenty, no oncoming vehicle"),
        }
    scene["your_answer_takes_effect_in_s"] = ANSWER_DELAY_S
    return scene


def radar_scene(world: World, rng: random.Random) -> dict:
    scene = compose(world, {"objects": []}, rng)
    scene.pop("camera", None)
    scene.pop("radar_only", None)
    return scene

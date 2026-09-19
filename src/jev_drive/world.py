from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

LANE_W = 3.5
ROAD_RIGHT, ROAD_LEFT = -LANE_W / 2, LANE_W * 1.5
SPEED_LIMIT = 50 / 3.6
SLOW_SPEED = 6.0
PASS_SPEED = 10.0
CAR_L, CAR_W = 4.5, 1.8
SENSOR_RANGE = 130.0
STOP_GAP = 9.0
STOP_GAP_LARGE = 12.0


def stop_gap(h) -> float:
    return STOP_GAP_LARGE if h.kind == "van" else STOP_GAP
MANEUVERS = ("cruise", "slow", "stop", "overtake")

PHRASES = {
    "van": ["a delivery van stopped in your lane with its hazard lights flashing",
            "a broken-down van in your lane, hazard lights on, nobody near it",
            "a parked van blocking your lane, its hazard lights blinking"],
    "boxes": ["a pile of cardboard boxes lying in your lane",
              "boxes that fell off a truck, scattered in your lane"],
    "cones": ["traffic cones closing your lane around a pothole",
              "a row of orange cones blocking your lane for road works"],
    "branch": ["a large fallen tree branch lying in your lane",
               "a broken tree limb covering your lane"],
    "ped_curb": ["a person standing at the edge of the sidewalk, facing the road",
                 "a pedestrian at the curb, looking toward the traffic"],
    "ped_phone": ["a person standing on the sidewalk near the curb, looking at their phone",
                  "someone waiting at a bus stop, looking down at a phone"],
    "ped_crossing": ["a person walking across the road",
                     "a pedestrian crossing the street in front of you"],
    "ped_parallel": ["a person walking along the sidewalk, parallel to the road",
                     "a jogger on the sidewalk, running in the same direction as the traffic"],
    "deer": ["a deer standing in your lane, looking at your car",
             "a deer in the middle of your lane, not moving"],
    "deer_leaving": ["a deer walking off the road toward the trees"],
    "dog_waiting": ["a dog without a leash on the far sidewalk, looking across the road",
                    "a loose dog sniffing around on the far sidewalk"],
    "dog_running": ["a dog running across the road",
                    "a dog dashing across the street"],
    "boxes_sudden": ["boxes that just fell off the truck in front of you, now lying in your lane",
                     "cargo that suddenly dropped from a truck onto your lane"],
    "ped_sudden": ["a person suddenly stepping into the road from behind a parked car",
                   "a child running into the street from between parked cars"],
    "deer_sudden": ["a deer that just jumped onto the road in front of you",
                    "a deer leaping out of the trees into your lane"],
}


@dataclass
class Body:
    x: float
    y: float
    length: float
    width: float
    vx: float = 0.0
    vy: float = 0.0

    @property
    def front(self) -> float:
        return self.x + self.length / 2

    @property
    def rear(self) -> float:
        return self.x - self.length / 2

    def overlaps(self, other: Body, margin: float = 0.0) -> bool:
        return (abs(self.x - other.x) * 2 < self.length + other.length + 2 * margin
                and abs(self.y - other.y) * 2 < self.width + other.width + 2 * margin)

    def spans_y(self, lo: float, hi: float) -> bool:
        return self.y + self.width / 2 > lo and self.y - self.width / 2 < hi


@dataclass
class Hazard(Body):
    kind: str = "van"
    id: int = 0
    behaviour: str = "static"
    state: str = "idle"
    phrase: dict = field(default_factory=dict)
    trigger_distance: float = 50.0
    timer: float = 0.0
    gone: bool = False
    outcome: dict = field(default_factory=dict)

    @property
    def static(self) -> bool:
        return self.behaviour == "static"

    @property
    def living(self) -> bool:
        return self.kind in ("pedestrian", "deer", "dog")

    def describe(self) -> str:
        return self.phrase.get(self.state) or self.phrase.get("idle", self.kind)


@dataclass
class OncomingCar(Body):
    id: int = 0
    cruise: float = 13.0
    colour: int = 0


@dataclass
class Ego(Body):
    maneuver: str = "cruise"
    phase: str = ""
    target_id: int | None = None
    accel: float = 0.0
    aeb: bool = False
    aeb_clear_s: float = 0.0


class World:
    def __init__(self, seed: int = 1, safety_floor: bool = True, hazard_gap_s: tuple[float, float] = (2.0, 6.0),
                 oncoming_headway_s: float = 5.0, sudden_share: float = 0.6, spawning: bool = True,
                 first_hazard_s: float = 2.0, kinds: dict[str, float] | None = None) -> None:
        self.sudden_share = sudden_share
        self.spawning = spawning
        self.seed = seed
        self.rng = random.Random(seed)
        self.safety_floor = safety_floor
        self.hazard_gap_s = hazard_gap_s
        self.oncoming_headway_s = oncoming_headway_s
        self.t = 0.0
        self.ego = Ego(x=0.0, y=0.0, length=CAR_L, width=CAR_W, vx=SPEED_LIMIT * 0.8)
        self.hazards: list[Hazard] = []
        self.oncoming: list[OncomingCar] = []
        self.events: list[dict] = []
        self.next_id = 1
        self.next_hazard_t = first_hazard_s
        self.kinds = kinds
        self.sudden_forced: bool | None = None
        self.next_oncoming_t = 0.0
        self.freeze_until = 0.0
        self.last_aeb_t = -99.0
        self.stats = {"distance_m": 0.0, "hazards": 0, "overtakes": 0, "crashes": 0, "safety_floor": 0,
                      "violations": 0, "unneeded_stop_s": 0.0, "stopped_s": 0.0, "time_s": 0.0, "sudden": 0}
        self.decision: dict = {}
        for _ in range(3):
            self._spawn_oncoming(self.ego.x + self.rng.uniform(40, 220))


    def log(self, kind: str, text: str, **extra) -> None:
        self.events.append({"t": round(self.t, 2), "kind": kind, "text": text, **extra})

    def _id(self) -> int:
        self.next_id += 1
        return self.next_id

    def _spawn_oncoming(self, x: float) -> None:
        cruise = self.rng.uniform(11.0, 15.0)
        self.oncoming.append(OncomingCar(x=x, y=LANE_W, length=CAR_L, width=CAR_W, vx=-cruise, id=self._id(),
                                         cruise=cruise, colour=self.rng.randrange(5)))

    def spawn_hazard(self, kind: str | None = None, distance: float | None = None, sudden: bool | None = None) -> Hazard:
        rng = self.rng
        if kind is None and self.kinds:
            kind = rng.choices(list(self.kinds), weights=list(self.kinds.values()))[0]
        if sudden is None and self.sudden_forced is not None and distance is None:
            sudden = self.sudden_forced
        if sudden is None:
            sudden = distance is None and kind in (None, "boxes", "pedestrian", "deer") and rng.random() < self.sudden_share
        if sudden:
            return self._spawn_sudden(kind)
        kind = kind or rng.choices(["van", "boxes", "cones", "branch", "pedestrian", "deer", "dog"],
                                   weights=[3, 1.5, 1.5, 1.5, 3.5, 2, 1.5])[0]
        x = self.ego.x + (distance if distance is not None else rng.uniform(85, 125))
        pick = lambda key: rng.choice(PHRASES[key])
        if kind in ("van", "boxes", "cones", "branch"):
            size = {"van": (5.5, 2.1), "boxes": (1.6, 1.8), "cones": (4.0, 2.2), "branch": (2.2, 2.6)}[kind]
            h = Hazard(x=x, y=rng.uniform(-0.2, 0.25), length=size[0], width=size[1], kind=kind, behaviour="static",
                       phrase={"idle": pick(kind)})
        elif kind == "pedestrian":
            behaviour = rng.choices(["crossing", "parallel", "waiting"], weights=[5, 3, 2])[0]
            if behaviour == "parallel":
                speed = rng.choice([1.4, -1.3, 2.6])
                h = Hazard(x=x, y=-3.1, length=0.6, width=0.6, vx=speed, kind=kind, behaviour=behaviour,
                           phrase={"idle": pick("ped_parallel")})
            else:
                looks = "ped_curb" if (behaviour == "crossing") == (rng.random() < 0.75) else "ped_phone"
                h = Hazard(x=x, y=-2.4, length=0.6, width=0.6, kind=kind, behaviour=behaviour,
                           trigger_distance=rng.uniform(28, 65),
                           phrase={"idle": pick(looks), "crossing": pick("ped_crossing")})
        elif kind == "deer":
            h = Hazard(x=x, y=rng.uniform(-0.3, 0.4), length=1.6, width=0.7, kind=kind, behaviour="deer",
                       timer=rng.uniform(4, 14), phrase={"idle": pick("deer"), "leaving": pick("deer_leaving")})
        else:
            h = Hazard(x=x, y=ROAD_LEFT + 1.2, length=0.9, width=0.5, kind="dog", behaviour="dog",
                       trigger_distance=rng.uniform(30, 55),
                       phrase={"idle": pick("dog_waiting"), "running": pick("dog_running")})
        h.id = self._id()
        self.hazards.append(h)
        self.stats["hazards"] += 1
        self.log("spawn", f"{h.describe()} appeared {x - self.ego.x:.0f} m ahead", hazard=h.id, hazard_kind=h.kind)
        return h

    def _spawn_sudden(self, kind: str | None = None) -> Hazard:
        rng = self.rng
        kind = kind or rng.choices(["boxes", "pedestrian", "deer"], weights=[3, 4, 3])[0]
        x = self.ego.x + rng.uniform(22, 45)
        if kind in ("van", "cones", "branch", "dog"):
            h = self.spawn_hazard(kind, distance=x - self.ego.x, sudden=False)
            self.stats["hazards"] -= 1
            self.events.pop()
            if kind == "dog":
                h.state, h.vy, h.y = "running", -rng.uniform(3.0, 4.5), ROAD_LEFT + 0.5
            h.outcome["sudden"] = True
            self.stats["hazards"] += 1
            self.stats["sudden"] += 1
            self.log("spawn", f"SUDDEN: {h.describe()}, {x - self.ego.x:.0f} m ahead", hazard=h.id, hazard_kind=h.kind,
                     sudden=True)
            return h
        if kind == "boxes":
            h = Hazard(x=x, y=rng.uniform(-0.2, 0.25), length=1.8, width=1.9, kind="boxes", behaviour="static",
                       phrase={"idle": rng.choice(PHRASES["boxes_sudden"])})
        elif kind == "pedestrian":
            h = Hazard(x=x, y=ROAD_RIGHT - 0.2, length=0.6, width=0.6, vy=rng.uniform(1.5, 2.2), kind="pedestrian",
                       behaviour="crossing", state="crossing", trigger_distance=0.0,
                       phrase={"idle": rng.choice(PHRASES["ped_sudden"]), "crossing": rng.choice(PHRASES["ped_sudden"])})
        else:
            h = Hazard(x=x, y=rng.uniform(-0.3, 0.4), length=1.6, width=0.7, kind="deer", behaviour="deer",
                       timer=rng.uniform(3, 8), phrase={"idle": rng.choice(PHRASES["deer_sudden"]),
                                                         "leaving": rng.choice(PHRASES["deer_leaving"])})
        h.id = self._id()
        h.outcome["sudden"] = True
        self.hazards.append(h)
        self.stats["hazards"] += 1
        self.stats["sudden"] += 1
        self.log("spawn", f"SUDDEN: {h.describe()}, {x - self.ego.x:.0f} m ahead", hazard=h.id, hazard_kind=h.kind,
                 sudden=True)
        return h


    def ahead(self, max_range: float = SENSOR_RANGE) -> list[Hazard]:
        e = self.ego
        return sorted((h for h in self.hazards if not h.gone and -8 < h.x - e.x < max_range),
                      key=lambda h: h.x)

    def blocking(self, h: Hazard, lo: float = ROAD_RIGHT, hi: float = LANE_W / 2) -> bool:
        return h.spans_y(lo, hi)

    def nearest_in_lane(self) -> Hazard | None:
        for h in self.ahead():
            if h.front > self.ego.rear and (self.blocking(h) or (h.living and h.state in ("crossing", "running"))):
                return h
        return None

    def oncoming_arrival(self, x: float) -> float | None:
        times = [(c.rear - x) / max(-c.vx, 0.5) for c in self.oncoming if c.rear > x - 2]
        return min(times) if times else None

    def pass_time(self, h: Hazard) -> float:
        e = self.ego
        x, y, v, t, dt, phase = e.x, e.y, e.vx, 0.0, 0.05, "out"
        while t < 30:
            target_y = 0.0 if phase == "back" else LANE_W
            rate = 1.8 if phase == "back" else min(1.8, 0.9 + 0.2 * v)
            y += max(-rate * dt, min(rate * dt, target_y - y))
            desired = PASS_SPEED
            if phase == "out":
                lo, hi = y - e.width / 2 - 0.3, y + e.width / 2 + 0.3
                if h.spans_y(lo, hi):
                    desired = min(desired, math.sqrt(max(0.0, 2 * 2.5 * (h.rear - (x + e.length / 2) - 1.5))))
                if y >= LANE_W - 0.1:
                    phase = "pass"
            v = max(0.0, v + max(-3.5, min(2.0, (desired - v) * 0.8)) * dt)
            x += v * dt
            t += dt
            if phase != "back" and x - e.length / 2 > h.front + 5.0:
                phase = "back"
            if phase == "back" and y + e.width / 2 < LANE_W / 2:
                return t
        return t


    def command(self, maneuver: str, source: str = "planner", **meta) -> None:
        if maneuver not in MANEUVERS:
            raise ValueError(maneuver)
        e = self.ego
        self.decision = {"maneuver": maneuver, "source": source, "t": round(self.t, 2), **meta}
        if e.phase:
            self.decision["note"] = "overtake in progress; finishing it first"
            return
        if maneuver == "overtake":
            target = self.nearest_in_lane()
            if target is None or target.x - e.x > 45:
                self.decision["note"] = "nothing close enough to overtake; holding speed"
                maneuver = "cruise" if target is None else "slow"
            elif e.vx > 3 and (target.rear - e.front) / e.vx < 2.3 / min(1.8, 0.9 + 0.2 * e.vx) + 0.5:
                self.decision["note"] = "too close to steer around at this speed; stopping first"
                maneuver = "stop"
            else:
                e.phase, e.target_id = "out", target.id
                self.stats["overtakes"] += 1
                self.log("overtake", f"overtaking {target.describe()}", hazard=target.id)
        if maneuver != e.maneuver:
            self.log("maneuver", f"{source}: {maneuver}", maneuver=maneuver)
        e.maneuver = maneuver

    def step(self, dt: float = 1 / 30) -> None:
        if self.t < self.freeze_until:
            self.t += dt
            return
        self.t += dt
        self.stats["time_s"] += dt
        self._spawn(dt)
        self._move_hazards(dt)
        self._move_oncoming(dt)
        self._control_ego(dt)
        self._check(dt)
        self._cleanup()

    def _spawn(self, dt: float) -> None:
        if self.t >= self.next_oncoming_t:
            far = self.ego.x + 240
            if not self.oncoming or max(c.x for c in self.oncoming) < far - 15:
                self._spawn_oncoming(far)
            self.next_oncoming_t = self.t + max(1.5, self.rng.expovariate(1 / self.oncoming_headway_s))
        active = any(not h.gone and h.x > self.ego.x - 10 for h in self.hazards)
        if active or not self.spawning:
            return
        if self.next_hazard_t == float("inf"):
            self.next_hazard_t = self.t + self.rng.uniform(*self.hazard_gap_s)
            self.log("clear", "road ahead clear")
        elif self.t >= self.next_hazard_t:
            self.spawn_hazard()
            self.next_hazard_t = float("inf")

    def _move_hazards(self, dt: float) -> None:
        e = self.ego
        for h in self.hazards:
            if h.gone:
                continue
            distance = h.x - e.x
            if h.behaviour == "crossing":
                if h.state == "idle" and distance < h.trigger_distance:
                    h.state, h.vy = "crossing", self.rng.uniform(1.2, 1.6)
                    self.log("hazard", "the pedestrian stepped onto the road", hazard=h.id)
                if h.y > ROAD_LEFT + 1.5:
                    h.gone = True
            elif h.behaviour == "dog":
                if h.state == "idle" and distance < h.trigger_distance:
                    h.state, h.vy = "running", -self.rng.uniform(3.0, 4.5)
                    self.log("hazard", "the dog ran onto the road", hazard=h.id)
                if h.y < ROAD_RIGHT - 2.5:
                    h.gone = True
            elif h.behaviour == "deer":
                if h.state == "idle":
                    h.timer -= dt
                    if h.timer <= 0 and distance < 60:
                        h.state, h.vy = "leaving", -0.9
                        self.log("hazard", "the deer started walking off the road", hazard=h.id)
                elif h.y < ROAD_RIGHT - 3:
                    h.gone = True
            h.x += h.vx * dt
            h.y += h.vy * dt

    def _move_oncoming(self, dt: float) -> None:
        e = self.ego
        ordered = sorted(self.oncoming, key=lambda c: c.x)
        for i, c in enumerate(ordered):
            target = c.cruise
            gap_limit = []
            if i > 0:
                gap_limit.append(c.rear - ordered[i - 1].front)
            if e.y > LANE_W / 2 - 0.3 and e.x < c.x:
                gap_limit.append(c.rear - e.front)
            for h in self.hazards:
                if not h.gone and h.living and h.spans_y(LANE_W / 2 - 0.5, ROAD_LEFT + 0.3) and h.x < c.x:
                    gap_limit.append(c.rear - h.front)
            speed = -c.vx
            if gap_limit and min(gap_limit) < 40:
                gap = min(gap_limit)
                target = 0.0 if gap < 12 else min(target, (gap - 12) * 0.6)
            accel = max(-6.0, min(2.0, (target - speed) * 1.5))
            c.vx = -max(0.0, speed + accel * dt)
            c.x += c.vx * dt

    def _control_ego(self, dt: float) -> None:
        e = self.ego
        target_h = next((h for h in self.hazards if h.id == e.target_id and not h.gone), None)
        lateral_target = 0.0
        if e.phase:
            if target_h is None and e.phase != "back":
                e.phase = "back"
            if e.phase == "out" and e.y >= LANE_W - 0.1:
                e.phase = "pass"
            if e.phase in ("out", "pass") and target_h is not None and e.rear > target_h.front + 5.0:
                e.phase = "back"
            lateral_target = 0.0 if e.phase == "back" else LANE_W
            if e.phase == "back" and abs(e.y) < 0.05:
                e.phase, e.target_id = "", None
                e.maneuver = "cruise"
                self.log("overtake", "back in lane")
            desired = PASS_SPEED
            if e.phase == "out" and target_h is not None:
                lo, hi = self._corridor()
                if target_h.spans_y(lo, hi):
                    room = target_h.rear - e.front - 1.5
                    desired = min(desired, math.sqrt(max(0.0, 2 * 2.5 * room)))
        elif e.maneuver == "cruise":
            desired = SPEED_LIMIT
        elif e.maneuver == "slow":
            desired = SLOW_SPEED
        else:
            desired = 0.0
        accel = self._longitudinal(desired)
        if e.maneuver == "stop" and not e.phase:
            accel = self._stop_accel()
        threat = self.safety_floor and self._threat()
        if threat:
            e.aeb_clear_s = 0.0
        elif e.aeb:
            e.aeb_clear_s += dt
        aeb = threat or (e.aeb and e.vx > 0.3 and e.aeb_clear_s < 0.5)
        if aeb:
            accel = -9.0
            if not e.aeb and self.t - self.last_aeb_t > 3.0:
                self.stats["safety_floor"] += 1
                self.log("safety", "SAFETY FLOOR: emergency braking", severity="high")
            if not e.aeb:
                self.last_aeb_t = self.t
            if e.phase in ("out", "pass") and self._oncoming_threat():
                target = next((h for h in self.hazards if h.id == e.target_id and not h.gone), None)
                if target is None or e.front < target.rear - 1.0:
                    e.phase = "back"
                    self.log("overtake", "overtake aborted: oncoming car too close")
                else:
                    aeb = False
                    accel = 2.5
                    if not e.aeb:
                        self.log("overtake", "oncoming car close: committing to finish the overtake")
        if not aeb and accel < -5 and e.vx > 1 and e.accel >= -5:
            self.log("brake", f"hard braking ({-accel:.1f} m/s²) on the planner's stop", severity="medium")
        e.aeb = aeb
        e.accel = accel
        e.vx = max(0.0, e.vx + accel * dt)
        e.x += e.vx * dt
        self.stats["distance_m"] += e.vx * dt
        if abs(lateral_target - e.y) > 0.01:
            rate = (1.8 if e.phase == "back" else min(1.8, 0.9 + 0.2 * e.vx)) * dt
            e.y += max(-rate, min(rate, lateral_target - e.y))
            e.vy = math.copysign(rate / dt, lateral_target - e.y)
        else:
            e.y, e.vy = lateral_target, 0.0

    def _longitudinal(self, desired: float) -> float:
        diff = desired - self.ego.vx
        return max(-3.5, min(2.0, diff * 0.8))

    def _stop_accel(self) -> float:
        e = self.ego
        h = self.nearest_in_lane() or next(iter(self.ahead(60)), None)
        if h is None:
            return max(-3.0, -e.vx * 2)
        room = (h.rear - stop_gap(h)) - e.front
        if room <= 0.3:
            return -min(9.0, max(3.0, e.vx * 4))
        need = e.vx ** 2 / (2 * room)
        if need > 1.2:
            return -min(9.0, need * 1.1)
        target = min(SLOW_SPEED, math.sqrt(2 * 1.0 * room))
        return max(-3.0, min(1.0, (target - e.vx) * 0.8))

    def _corridor(self) -> tuple[float, float]:
        e = self.ego
        return e.y - e.width / 2 - 0.3, e.y + e.width / 2 + 0.3

    def _oncoming_threat(self) -> bool:
        e = self.ego
        if e.phase == "back":
            return False
        lo, hi = self._corridor()
        for c in self.oncoming:
            if c.spans_y(lo, hi) and c.x > e.x:
                gap = c.rear - e.front
                closing = e.vx - c.vx
                if gap < 0 or (closing > 0 and gap / closing < 2.2):
                    return True
        return False

    def _threat(self) -> bool:
        e = self.ego
        if e.vx < 0.2:
            return False
        lo, hi = self._corridor()
        for h in self.hazards:
            if h.gone or h.x < e.x:
                continue
            gap = h.rear - e.front
            closing = e.vx - h.vx
            if closing <= 0.1:
                continue
            t_reach = max(0.0, gap) / closing
            y_then = h.y + h.vy * t_reach
            inside_now, inside_then = h.spans_y(lo, hi), (y_then + h.width / 2 > lo and y_then - h.width / 2 < hi)
            if not (inside_now or inside_then):
                continue
            need = closing ** 2 / (2 * max(gap - 2.0, 0.1))
            if need > 6.0 or (gap < 2.5 and closing > 1.0):
                return True
        return self._oncoming_threat()

    def _check(self, dt: float) -> None:
        e = self.ego
        for obj in [*self.hazards, *self.oncoming]:
            if getattr(obj, "gone", False):
                continue
            if e.overlaps(obj):
                self._crash(obj)
                return
        if e.y > LANE_W / 2:
            for h in self.hazards:
                if (not h.gone and h.living and h.spans_y(ROAD_RIGHT, ROAD_LEFT) and abs(h.x - e.x) < 12
                        and not h.outcome.get("violation")):
                    h.outcome["violation"] = True
                    self.stats["violations"] += 1
                    self.log("violation", f"drove around {h.describe()} while it was on the road", hazard=h.id)
        if e.vx < 0.3:
            self.stats["stopped_s"] += dt
        if e.vx < 0.3 and not e.phase:
            h = self.nearest_in_lane()
            near = [x for x in self.ahead(40) if x.living and x.spans_y(ROAD_RIGHT - 1.2, ROAD_LEFT + 1.2)]
            if h is None and not near:
                self.stats["unneeded_stop_s"] += dt

    def _crash(self, obj) -> None:
        e = self.ego
        what = obj.describe() if isinstance(obj, Hazard) else "an oncoming car"
        self.stats["crashes"] += 1
        self.log("crash", f"CRASH into {what} at {e.vx * 3.6:.0f} km/h", severity="high")
        if isinstance(obj, Hazard):
            obj.gone = True
        else:
            self.oncoming.remove(obj)
        e.vx, e.y, e.phase, e.target_id, e.maneuver = 0.0, 0.0, "", None, "cruise"
        self.freeze_until = self.t + 2.0

    def _cleanup(self) -> None:
        e = self.ego
        for h in self.hazards:
            if not h.gone and h.x < e.x - 15:
                h.gone = True
        self.hazards = [h for h in self.hazards if not h.gone or h.x > e.x - 60]
        self.oncoming = [c for c in self.oncoming if c.x > e.x - 80]


    def snapshot(self) -> dict:
        e = self.ego
        return {
            "t": round(self.t, 2),
            "ego": {"x": round(e.x, 2), "y": round(e.y, 3), "v": round(e.vx, 2), "vy": round(e.vy, 2), "a": round(e.accel, 2),
                    "maneuver": e.maneuver, "phase": e.phase, "aeb": e.aeb,
                    "brake": "emergency" if e.aeb else "hard" if e.accel < -5 and e.vx > 0.3 else
                             "normal" if e.accel < -1 else ""},
            "hazards": [{"id": h.id, "kind": h.kind, "x": round(h.x, 2), "y": round(h.y, 2), "l": h.length, "w": h.width,
                         "vx": round(h.vx, 2), "vy": round(h.vy, 2), "state": h.state, "text": h.describe(),
                         "sudden": bool(h.outcome.get("sudden"))} for h in self.hazards if not h.gone],
            "target": self.ego.target_id or (self.nearest_in_lane().id if self.nearest_in_lane() else None),
            "oncoming": [{"id": c.id, "x": round(c.x, 2), "y": c.y, "v": round(-c.vx, 2), "c": c.colour}
                         for c in self.oncoming],
            "stats": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in self.stats.items()},
            "decision": self.decision,
            "frozen": self.t < self.freeze_until,
        }

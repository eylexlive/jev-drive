from __future__ import annotations

import base64
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path

from .client import Client
from . import director as director_mod
from .planners import JevPlanner, LLMPlanner, RulePlanner, VisionLLMPlanner, describe
from .vision.llm_driver import LLMDriver
from .vision.bridge import TYPES, RenderBridge
from .vision.perceive import LANE_RULE, Camera, cued_prompt
from .vision.sensors import compose, fuse, radar, radar_scene
from .world import World

FPS = 30


TAKE_VAN_DISTANCE_M = 110.0


HAZARD_KINDS = ("van", "boxes", "cones", "branch", "pedestrian", "deer", "dog")


def export_take(raw: Path, final: Path) -> None:
    if not shutil.which("ffmpeg"):
        print(f"ffmpeg not found; the raw recording is at {raw}", file=sys.stderr)
        return
    part = final.with_suffix(".part.mp4")
    codec = ["-c:v", "h264_videotoolbox", "-b:v", "14M"] if sys.platform == "darwin" else ["-c:v", "libx264", "-crf", "18"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-vf", "fps=30,scale=1920:-2", *codec,
                    "-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(part)],
                   check=False)
    if part.exists() and part.stat().st_size > 0:
        part.rename(final)


class Session:
    def __init__(self, seed: int, planner: str, client: Client | None, log_dir: Path | None, safety_floor: bool = True,
                 world_kwargs: dict | None = None, shadow: bool = True):
        self.lock = threading.Lock()
        self.running, self.stop = threading.Event(), threading.Event()
        self.client, self.seed, self.log_dir = client, seed, log_dir
        self.world_kwargs = world_kwargs or {}
        self.world = World(seed=seed, safety_floor=safety_floor, **self.world_kwargs)
        self.rules = RulePlanner()
        self.jev = JevPlanner(client) if client else None
        openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))
        self.gemini = LLMPlanner(LLMDriver()) if client and openrouter else None
        self.sudden_setting: bool | None = None
        self.shadow_enabled = shadow
        self.agreement = {"same": 0, "different": 0}
        self.race: dict = {}
        self.view_mode = "chase"
        self.last_take: str | None = None
        self.director = {"active": False, "t0": 0.0, "done": [], "last": None, "caption": "", "seq": 0}
        self.jev_thread: threading.Thread | None = None
        self.next_rule_t = 0.0
        self.events_written = 0
        self.viewers = 0
        self.last_viewer = time.monotonic()
        self.idle_pause_s = 10.0
        self.eye = "code"
        self.bridge = RenderBridge()
        self.camera = Camera() if client and openrouter else None
        self.e2e_frame: bytes | None = None
        self.take: dict | None = None
        self.vision = VisionLLMPlanner(LLMDriver(), lambda: self.e2e_frame) if client and openrouter else None
        available = {"rules": True, "jev": self.jev, "gemini": self.gemini, "gemini_vision": self.vision}
        self.planner = planner if available.get(planner) else ("jev" if self.jev else "rules")
        self.camera_info: dict = {"frame": 0, "objects": [], "latency_ms": None, "cost_usd": 0.0, "error": None}
        self.last_jpeg: bytes | None = None
        self.radar_rng = random.Random(1)
        self.perception: dict | None = None
        self.camera_period_s = 1.0
        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)


    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()
        if self.camera:
            threading.Thread(target=self._camera_loop, daemon=True).start()
        if self.jev:
            threading.Thread(target=self._director_loop, daemon=True).start()
        if self.gemini:
            threading.Thread(target=self._gemini_loop, daemon=True).start()
        if self.vision:
            threading.Thread(target=self._vision_loop, daemon=True).start()
        threading.Thread(target=self._take_loop, daemon=True).start()
        if self.jev:
            self.jev_thread = threading.Thread(target=self._jev_loop, daemon=True)
            self.jev_thread.start()
        if not self.take:
            self.running.set()

    def _jev_loop(self) -> None:
        self.jev.run(lambda: self.world, self.lock, lambda: self.running.is_set() and self.planner == "jev",
                     self.stop, on_decision=self._on_driver_decision, observe=self._observe, on_scene=self._on_scene)

    def _gemini_loop(self) -> None:
        self.gemini.run(lambda: self.world, self.lock, lambda: self.running.is_set() and self.planner == "gemini",
                        self.stop, on_decision=self._on_driver_decision, observe=self._observe, on_scene=self._on_scene)

    def setup_take(self) -> None:
        self.seed += 1
        self.world = World(seed=self.seed, safety_floor=True,
                           **{**self.world_kwargs, "spawning": False, "oncoming_headway_s": 1e9})
        w = self.world
        w.oncoming.clear()
        for ahead in (70.0, 150.0, 230.0):
            w._spawn_oncoming(w.ego.x + ahead)
        w.next_oncoming_t = float("inf")
        w.next_hazard_t = float("inf")
        w.ego.vx = 0.0
        self.eye, self.planner, self.view_mode = "code", "jev" if self.jev else "rules", "chase"
        self.perception = None
        self.camera_info = {**self.camera_info, "objects": []}
        self.events_written, self.next_rule_t = 0, 0.0
        self.take = {"world": w, "van": None, "camera_at": None, "boxes": False, "early_car": False, "traffic": False}
        self.running.clear()

    def _take_loop(self) -> None:
        while not self.stop.is_set():
            time.sleep(0.1)
            take = self.take
            if not take or not self.running.is_set():
                continue
            with self.lock:
                w = self.world
                if w is not take["world"]:
                    continue
                e = w.ego
                if not take["early_car"] and w.t >= 3.0:
                    take["early_car"] = True
                    w._spawn_oncoming(e.x + 240)
                if take["van"] is None and w.t >= 9.0:
                    take["van"] = w.spawn_hazard("van", distance=TAKE_VAN_DISTANCE_M, sudden=False)
                van = take["van"]
                van_passed = van is not None and van.front < e.rear - 10 and not e.phase
                if take["camera_at"] is None and van_passed and w.t >= 22.0:
                    take["camera_at"] = w.t
                    if self.camera:
                        self.eye = "camera"
                        w.log("planner", "eye switched to camera")
                if take["boxes"] is False and take["camera_at"] is not None and w.t >= max(30.0, take["camera_at"] + 6.0):
                    take["boxes"] = w.spawn_hazard("boxes", sudden=True)
                boxes = take["boxes"]
                if not take["traffic"] and boxes and boxes.front < e.rear - 10 and not e.phase:
                    take["traffic"] = True
                    w.oncoming_headway_s = 6.0
                    w.next_oncoming_t = w.t

    def _vision_loop(self) -> None:
        self.vision.run(lambda: self.world, self.lock, lambda: self.running.is_set() and self.planner == "gemini_vision",
                        self.stop, on_decision=self._on_driver_decision, observe=self._observe_frame)

    def _observe_frame(self, world_fn, lock):
        with lock:
            world = world_fn()
            snapshot, captured_t = world.snapshot(), world.t
            scene = radar_scene(world, self.radar_rng)
        jpeg = self.bridge.render(snapshot, timeout=20)
        self.e2e_frame = self.last_jpeg = jpeg
        self.camera_info = {**self.camera_info, "frame": self.camera_info["frame"] + 1, "objects": []}
        with lock:
            scene["camera_frame_age_s"] = round(world.t - captured_t, 1)
        return world, scene

    def _director_loop(self) -> None:
        while not self.stop.is_set():
            time.sleep(director_mod.PERIOD_S)
            d = self.director
            if not d["active"]:
                continue
            seconds = time.time() - d["t0"]
            with self.lock:
                ahead = next((h for h in self.world.ahead(120) if h.spans_y(-2.0, 2.0) or h.living), None)
                e = self.world.ego
                car = e.maneuver + (" (overtaking)" if e.phase else "") + f", {e.vx * 3.6:.0f} km/h"
            since_last = seconds - (d["done"][-1]["t"] if d["done"] else 0.0)
            state = director_mod.director_state(seconds, since_last, self.view_mode, d["done"],
                                                ahead.describe() if ahead else None, car)
            try:
                result = self.jev.client.ask(state, director_mod.QUESTION)
                answer = result["answers"]["button"]
                action = answer.get("choice")
            except Exception as exc:
                d["error"] = str(exc)[:120]
                continue
            overtime = seconds > director_mod.TAKE_S + 5
            if overtime:
                action = "finish"
            if action not in director_mod.ACTIONS or action == "wait":
                continue
            if not overtime and action != director_mod.next_step(d["done"]):
                continue
            if not overtime and d["done"] and seconds - d["done"][-1]["t"] < 4.0:
                continue
            self._director_press(action, seconds, answer.get("probabilities") or {})

    def _director_press(self, action: str, seconds: float, probabilities: dict) -> None:
        d = self.director
        with self.lock:
            if action.startswith("view_"):
                self.view_mode = action.split("_", 1)[1].replace("cinematic", "side")
            elif action in ("spawn_van", "spawn_boxes", "spawn_person"):
                if any(not h.gone and h.x > self.world.ego.x - 10 for h in self.world.hazards):
                    return
                if action == "spawn_van":
                    self.world.spawn_hazard("van", distance=100.0, sudden=False)
                elif action == "spawn_boxes":
                    self.world.spawn_hazard("boxes", sudden=True)
                else:
                    self.world.spawn_hazard("pedestrian", sudden=True)
            elif action == "finish":
                d["active"] = False
                self.running.clear()
        d["done"].append({"action": action, "t": round(seconds, 1)})
        d["seq"] += 1
        d["last"] = {"action": action, "t": round(seconds, 1), "seq": d["seq"],
                     "p": round(float(probabilities.get(action, 0.0)), 2)}
        d["caption"] = director_mod.CAPTIONS.get(action, d["caption"])

    def _on_scene(self, scene: dict) -> None:
        if not (self.shadow_enabled and self.planner in ("jev", "gemini")):
            return
        frame = self.camera_info["frame"] if self.eye == "camera" else int(time.time())
        if frame == self.race.get("frame") or self.race.get("busy"):
            return
        other = self.gemini if self.planner == "jev" else self.jev
        if other is None:
            return
        started = time.time()
        self.race = {"frame": frame, "started": started, "busy": True, "answers": {}}

        def shadow():
            try:
                choice, probs, result = other.ask(scene)
                other.status.record(choice, probs, result, scene)
                self._race_answer(other.name, choice, started)
            except Exception as exc:
                other.status.errors += 1
                other.status.last_error = f"{type(exc).__name__}: {exc}"[:160]
            finally:
                self.race["busy"] = False
        threading.Thread(target=shadow, daemon=True).start()

    def _race_answer(self, name: str, choice: str, started: float) -> None:
        race = self.race
        if race.get("started") != started:
            return
        race["answers"][name] = {"choice": choice, "after_s": round(time.time() - started, 2)}
        if len(race["answers"]) == 2:
            a, b = race["answers"].values()
            self.agreement["same" if a["choice"] == b["choice"] else "different"] += 1

    def _camera_loop(self) -> None:
        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(max_workers=3)
        in_flight = 0
        lock = threading.Lock()

        def perceive(world, snapshot, captured_t, hint):
            nonlocal in_flight
            try:
                started = time.perf_counter()
                jpeg = self.bridge.render(snapshot, timeout=20)
                seen = self.camera.describe(jpeg, hint)
                fresher = self.perception is None or self.perception["world"] is not world \
                    or captured_t > self.perception["captured_t"]
                if fresher:
                    self.perception = {"seen": seen, "captured_t": captured_t, "world": world}
                    self.last_jpeg = jpeg
                    with self.lock:
                        shown = fuse(seen["objects"], radar(world, random.Random(0)), world.ego.vx)
                    self.camera_info = {"frame": self.camera_info["frame"] + 1, "objects": shown,
                                        "latency_ms": round((time.perf_counter() - started) * 1000),
                                        "cost_usd": round(self.camera.cost_usd, 4), "error": None}
            except Exception as exc:
                self.camera_info = {**self.camera_info, "error": f"{type(exc).__name__}: {exc}"[:160]}
            finally:
                with lock:
                    in_flight -= 1

        while not self.stop.is_set():
            active = self.eye == "camera" and self.planner in ("jev", "gemini") and self.running.is_set()
            if active and in_flight < 3:
                with self.lock:
                    world = self.world
                    snapshot, captured_t = world.snapshot(), world.t
                    hint = LANE_RULE + cued_prompt(radar(world, random.Random(0)))
                with lock:
                    in_flight += 1
                pool.submit(perceive, world, snapshot, captured_t, hint)
            time.sleep(self.camera_period_s)

    def _observe(self, world_fn, lock):
        if self.eye != "camera" or self.camera is None:
            with lock:
                world = world_fn()
                return world, describe(world)
        waited = 0.0
        while self.perception is None or self.perception["world"] is not world_fn():
            if waited > 20:
                raise TimeoutError("no camera report yet; is the viewer page open?")
            time.sleep(0.1)
            waited += 0.1
        with lock:
            world = world_fn()
            report = self.perception
            scene = compose(world, report["seen"], self.radar_rng)
            scene["camera_report_age_s"] = round(world.t - report["captured_t"], 1)
            return world, scene

    def _loop(self) -> None:
        dt = 1 / FPS
        next_tick = time.perf_counter()
        while not self.stop.is_set():
            next_tick += dt
            if self.viewers > 0:
                self.last_viewer = time.monotonic()
            elif self.running.is_set() and time.monotonic() - self.last_viewer > self.idle_pause_s:
                self.running.clear()
                with self.lock:
                    self.world.log("planner", "paused: nobody is watching")
            if self.running.is_set():
                with self.lock:
                    w = self.world
                    try:
                        w.step(dt)
                    except Exception:
                        traceback.print_exc()
                        if self.log_dir:
                            with (self.log_dir / "loop_errors.log").open("a") as f:
                                f.write(traceback.format_exc() + "\n")
                    if self.planner == "rules" and w.t >= self.next_rule_t:
                        choice = self.rules.choose(w)
                        if choice != w.ego.maneuver or w.decision.get("source") != "rules":
                            w.command(choice, "rules")
                        self.next_rule_t = w.t + 0.5
                    self._flush_events()
            sleep = next_tick - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_tick = time.perf_counter()

    def _flush_events(self) -> None:
        if not self.log_dir:
            return
        new = self.world.events[self.events_written:]
        if new:
            with (self.log_dir / "events.jsonl").open("a") as f:
                for e in new:
                    f.write(json.dumps({**e, "planner": self.planner, "seed": self.seed}) + "\n")
            self.events_written = len(self.world.events)

    def _on_driver_decision(self, row: dict) -> None:
        race = self.race
        if race.get("started") and row.get("driver") and row["driver"] not in race.get("answers", {}):
            self._race_answer(row["driver"], row["choice"], race["started"])
        self._log_decision(row)

    def _log_decision(self, row: dict) -> None:
        if self.log_dir:
            with (self.log_dir / "decisions.jsonl").open("a") as f:
                f.write(json.dumps({**row, "seed": self.seed}) + "\n")


    def control(self, body: dict) -> dict:
        action = body.get("action")
        with self.lock:
            if action == "pause":
                self.running.clear()
            elif action == "resume":
                self.running.set()
            elif action == "reset" and self.take:
                self.setup_take()
            elif action == "reset":
                self.seed = int(body.get("seed") or self.seed + 1)
                self.world = World(seed=self.seed, safety_floor=self.world.safety_floor, **self.world_kwargs)
                self.world.sudden_forced = self.sudden_setting
                self.perception = None
                self.camera_info = {**self.camera_info, "objects": []}
                self.events_written, self.next_rule_t = 0, 0.0
            elif action == "planner":
                wanted = body.get("planner")
                if wanted in ("jev", "gemini") and not self.jev:
                    return {"ok": False, "error": "Models are not available: start the server with an API key"}
                if wanted in ("gemini", "gemini_vision") and not self.gemini:
                    return {"ok": False, "error": "The Gemini driver needs OPENROUTER_API_KEY"}
                if wanted in ("jev", "gemini", "gemini_vision", "rules"):
                    if wanted == "gemini_vision":
                        self.eye = "code"
                    self.planner = wanted
                    self.world.log("planner", f"driver switched to {wanted}")
            elif action == "hazards":
                kinds = [k for k in body.get("kinds") or [] if k in HAZARD_KINDS]
                if kinds:
                    self.world_kwargs["kinds"] = {k: 1.0 for k in kinds}
                    self.world.kinds = self.world_kwargs["kinds"]
                if body.get("interval_s") is not None:
                    gap = max(3.0, min(120.0, float(body["interval_s"])))
                    self.world_kwargs["hazard_gap_s"] = (gap, gap)
                    self.world.hazard_gap_s = (gap, gap)
                    if self.world.next_hazard_t != float("inf"):
                        self.world.next_hazard_t = min(self.world.next_hazard_t, self.world.t + gap)
                if "sudden" in body:
                    self.sudden_setting = bool(body["sudden"])
                    self.world.sudden_forced = self.sudden_setting
                    self.world_kwargs["sudden_share"] = 1.0 if body["sudden"] else 0.0
            elif action == "spawn":
                kind = body.get("kind")
                if kind not in HAZARD_KINDS:
                    kind = None
                if any(not h.gone and h.x > self.world.ego.x - 10 for h in self.world.hazards):
                    return {"ok": False, "error": "There is already an obstacle ahead; wait until it is behind you"}
                self.world.spawn_hazard(kind, sudden=bool(body.get("sudden")) if "sudden" in body else None)
                self.world.next_hazard_t = float("inf")
            elif action == "view":
                if body.get("view") in ("chase", "dash", "side", "drone"):
                    self.view_mode = body["view"]
            elif action == "director":
                if body.get("on"):
                    if not self.jev:
                        return {"ok": False, "error": "The director needs Jev (an API key)"}
                    self.seed += 1
                    self.world = World(seed=self.seed, safety_floor=self.world.safety_floor,
                                       **{**self.world_kwargs, "spawning": False, "oncoming_headway_s": 14.0})
                    self.world.oncoming = [c for c in self.world.oncoming if c.x > self.world.ego.x + 150]
                    self.perception = None
                    self.camera_info = {**self.camera_info, "objects": []}
                    self.events_written, self.next_rule_t = 0, 0.0
                    self.view_mode = "chase"
                    self.world.ego.vx = 0.0
                    self.director = {"active": True, "t0": time.time(), "done": [], "last": None, "seq": 0,
                                     "caption": director_mod.CAPTIONS["start"]}
                    self.running.set()
                else:
                    self.director["active"] = False
            elif action == "eye":
                wanted = body.get("eye")
                if wanted == "camera" and self.planner == "gemini_vision":
                    return {"ok": False, "error": "This driver looks at the camera frame itself; pick another driver first"}
                if wanted == "camera" and self.camera is None:
                    return {"ok": False, "error": "The camera eye needs an API key (OpenRouter)"}
                if wanted in ("code", "camera"):
                    self.eye = wanted
                    self.world.log("planner", f"eye switched to {wanted}")
            elif action == "floor":
                self.world.safety_floor = bool(body.get("on"))
                self.world.log("planner", f"safety floor {'on' if self.world.safety_floor else 'off'}")
            else:
                return {"ok": False, "error": f"unknown action {action!r}"}
        return {"ok": True}

    def view(self) -> dict:
        with self.lock:
            snap = self.world.snapshot()
            snap["events"] = self.world.events[-14:]
            scene = describe(self.world)
            snap["code_ahead"] = scene["ahead"] if isinstance(scene["ahead"], list) else []
        driving = {"jev": self.jev, "gemini": self.gemini, "gemini_vision": self.vision}.get(self.planner)
        status = (driving.status if driving else self.rules.status).public()
        if self.planner == "rules":
            status["scene"] = scene
        snap.update(planner=self.planner, planner_status=status, running=self.running.is_set(), seed=self.seed,
                    jev_available=bool(self.jev), safety_floor=self.world.safety_floor, eye=self.eye,
                    camera=self.camera_info, camera_model=self.camera.model if self.camera else None,
                    models={name: {k: v for k, v in planner.status.public().items() if k != "scene"}
                            for name, planner in (("jev", self.jev), ("gemini", self.gemini),
                                                  ("gemini_vision", self.vision)) if planner},
                    agreement=self.agreement,
                    race={"frame": self.race.get("frame"), "answers": self.race.get("answers", {})},
                    view=self.view_mode, last_take=self.last_take,
                    director={"active": self.director["active"], "last": self.director["last"],
                              "caption": self.director["caption"],
                              "elapsed_s": round(time.time() - self.director["t0"], 1) if self.director["active"] else None},
                    hazard_settings={"kinds": list(self.world.kinds or HAZARD_KINDS),
                                     "interval_s": self.world.hazard_gap_s[0],
                                     "sudden": self.world.sudden_forced if self.world.sudden_forced is not None
                                     else self.world.sudden_share >= 0.5})
        return snap


def make_handler(session: Session):
    web = resources.files("jev_drive").joinpath("web")
    classic = web.joinpath("index.html").read_bytes()
    dist = Path(str(web.joinpath("dist")))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/2d", "/classic"):
                self._send(200, classic, "text/html; charset=utf-8")
            elif path in ("/", "/index.html") or path.startswith(("/assets/", "/models/", "/favicon")):
                target = (dist / ("index.html" if path in ("/", "/index.html") else path.lstrip("/"))).resolve()
                if dist.resolve() not in target.parents or not target.is_file():
                    if path == "/" and not (dist / "index.html").exists():
                        return self._send(200, classic, "text/html; charset=utf-8")
                    return self._send(404, b"not found", "text/plain")
                self._send(200, target.read_bytes(), TYPES.get(target.suffix, "application/octet-stream"))
            elif path == "/render/next":
                job = session.bridge.next_job()
                if job is None:
                    return self._send(204, b"", "text/plain")
                self._send(200, json.dumps(job).encode(), "application/json")
            elif path == "/camera/latest.jpg":
                if session.last_jpeg is None:
                    return self._send(404, b"no frame yet", "text/plain")
                self._send(200, session.last_jpeg, "image/jpeg")
            elif path == "/state":
                self._send(200, json.dumps(session.view()).encode(), "application/json")
            elif self.path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                session.viewers += 1
                try:
                    while not session.stop.is_set():
                        self.wfile.write(f"data: {json.dumps(session.view())}\n\n".encode())
                        self.wfile.flush()
                        time.sleep(1 / 20)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    session.viewers -= 1
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path.startswith("/take/upload"):
                length = int(self.headers.get("Content-Length") or 0)
                if length > 600_000_000:
                    return self._send(413, b'{"ok": false, "error": "too large"}', "application/json")
                kind = "mp4" if "mp4" in (self.headers.get("Content-Type") or "") else "webm"
                folder = Path("runs/takes")
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"take-{time.strftime('%Y%m%d-%H%M%S')}.{kind}"
                path.write_bytes(self.rfile.read(length))
                session.last_take = str(path)
                final = Path.home() / "Downloads" / f"jev-drive-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
                threading.Thread(target=export_take, args=(path, final), daemon=True).start()
                return self._send(200, json.dumps({"ok": True, "path": str(final)}).encode(), "application/json")
            if self.path == "/render/result":
                length = min(int(self.headers.get("Content-Length") or 0), 20_000_000)
                body = json.loads(self.rfile.read(length))
                session.bridge.deliver(body["id"], base64.b64decode(body["jpeg"].split(",", 1)[1]), body.get("boxes"))
                return self._send(200, b'{"ok": true}', "application/json")
            if self.path != "/control":
                return self._send(404, b"not found", "text/plain")
            length = min(int(self.headers.get("Content-Length") or 0), 10_000)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._send(400, b'{"ok": false, "error": "bad json"}', "application/json")
            self._send(200, json.dumps(session.control(body)).encode(), "application/json")

        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def serve(session: Session, port: int = 8765) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(session))
    server.daemon_threads = True
    session.start()
    return server

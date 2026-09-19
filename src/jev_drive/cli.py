from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

from .client import ClientError, make_client
from .planners import QUESTIONS, describe
from .server import Session, serve
from .world import World


def cmd_serve(args) -> int:
    client = None
    if not args.no_jev:
        client = make_client(args.provider, args.model)
        try:
            client.check_key()
        except ClientError as exc:
            print(f"Jev unavailable ({exc}); starting with the rule planner only", file=sys.stderr)
            client = None
    log_dir = None if args.no_log else Path(args.log_dir) / time.strftime("%Y%m%d-%H%M%S")
    paces = {
        "normal": {},
        "video": {"first_hazard_s": 15.0, "hazard_gap_s": (12.0, 16.0), "sudden_share": 0.5, "oncoming_headway_s": 9.0,
                  "kinds": {"boxes": 3, "van": 3, "pedestrian": 1, "deer": 1}},
    }
    session = Session(seed=args.seed, planner=args.planner, client=client, log_dir=log_dir,
                      world_kwargs=paces[args.pace], shadow=not args.no_shadow)
    if args.take:
        session.setup_take()
    if args.eye == "camera":
        if session.camera is None:
            print("the camera eye needs an API key; starting with the code eye", file=sys.stderr)
        else:
            session.eye = "camera"
    server = serve(session, args.port)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"jev-drive running at {url}  (driver: {session.planner}; Ctrl+C to stop)")
    if log_dir:
        print(f"logging events and decisions to {log_dir}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.stop.set()
        server.server_close()
    return 0


def cmd_scene(args) -> int:
    world = World(seed=args.seed)
    while world.t < args.at:
        world.step()
    print(json.dumps({"state": describe(world), "questions": QUESTIONS}, indent=2))
    return 0


ARMS = ("jev", "keyword", "radar_only", "gemini_reads", "gemini_sees")


def cmd_eval(args) -> int:
    from .client import Cache
    from .eval.scenes import standard_set
    from .vision.bridge import RenderBridge, serve as serve_bridge
    from .vision.llm_driver import LLMDriver
    from .vision.perceive import Camera
    from .vision.run import Budget, VisionGemini, VisionJev, VisionKeyword, VisionRadarOnly, run_all

    wanted = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in wanted if a not in ARMS]
    if unknown:
        print(f"unknown arms {unknown}; choose from {', '.join(ARMS)}", file=sys.stderr)
        return 2
    scenes = standard_set(seed=args.seed)
    if args.limit:
        step = max(1, len(scenes) // args.limit)
        scenes = scenes[::step][:args.limit]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    arms, jev = [], None
    if "jev" in wanted:
        client = make_client(args.provider)
        client.check_key()
        jev = VisionJev(client, Cache(out / "jev_cache.jsonl"))
        arms.append(jev)
    arms += [VisionKeyword()] if "keyword" in wanted else []
    arms += [VisionRadarOnly()] if "radar_only" in wanted else []
    for name in ("gemini_reads", "gemini_sees"):
        if name in wanted:
            arms.append(VisionGemini(LLMDriver(), Cache(out / f"{name}_cache.jsonl"), sees=name == "gemini_sees"))
    camera = Camera(cache_path=out / "camera_cache.jsonl")
    budget = Budget(args.budget, camera, *[a for a in arms if hasattr(a, "cost_usd")])
    bridge = RenderBridge()
    serve_bridge(bridge, args.port)
    print(f"{len(scenes)} scenes x {len(arms)} arms. Open http://127.0.0.1:{args.port}/?render=1 in a browser "
          "and keep it visible.")
    started = time.time()
    run_all(scenes, arms, bridge, camera, out / "episodes.jsonl", budget, workers=args.workers)
    print(f"done in {time.time() - started:.0f} s, spent ${budget.spent:.2f}; episodes in {out / 'episodes.jsonl'}")
    return 0


def cmd_dataset(args) -> int:
    from .vision.bridge import RenderBridge, serve as serve_bridge
    from .vision.dataset import build_dataset

    bridge = RenderBridge()
    serve_bridge(bridge, args.port)
    print(f"Open http://127.0.0.1:{args.port}/?render=1 in a browser and keep it visible.")
    n = build_dataset(Path(args.out), bridge, seed=args.seed)
    print(f"{n} frames with ground truth in {args.out}")
    return 0


def cmd_bench_eye(args) -> int:
    from .vision.bench import ensure_frames, run
    from .vision.eyes import load_eye

    data = Path(args.data)
    ensure_frames(data)
    eye = load_eye(args.eye)
    out = Path(args.out) / f"{eye.name}.jsonl"
    print(json.dumps(run(eye, data, out, limit=args.limit, budget_usd=args.budget), indent=1))
    return 0


def cmd_report(args) -> int:
    from .vision.report import analyse

    print(json.dumps(analyse(Path(args.episodes)), indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jev-drive", description="Watch Jev, a decision model, drive a simulated road with sudden hazards.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("serve", help="run the simulation and the viewer")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--planner", choices=("jev", "gemini", "gemini_vision", "rules"), default="jev",
                   help="gemini_vision: Gemini looks at the camera frame and decides by itself")
    p.add_argument("--pace", choices=("normal", "video"), default="normal", help="video: fewer, well-spaced obstacles")
    p.add_argument("--take", action="store_true",
                   help="a scripted ~45 s recording: start from rest, a van at 9 s, camera eye, sudden boxes; press play to start")
    p.add_argument("--no-shadow", action="store_true", help="do not ask the other model for the side-by-side view")
    p.add_argument("--provider", choices=("openrouter", "typesafe"), default="openrouter")
    p.add_argument("--model")
    p.add_argument("--no-jev", action="store_true", help="rule planner only; no API key needed")
    p.add_argument("--eye", choices=("code", "camera"), default="code",
                   help="camera: a vision model describes the rendered windscreen view (needs the viewer open)")
    p.add_argument("--open", action="store_true", help="open the viewer in the default browser")
    p.add_argument("--log-dir", default="runs")
    p.add_argument("--no-log", action="store_true")
    p.set_defaults(func=cmd_serve)
    p = sub.add_parser("scene", help="print the exact request for a moment of a road; sends nothing")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--at", type=float, default=6.0, help="seconds into the road")
    p.set_defaults(func=cmd_scene)
    p = sub.add_parser("eval", help="vision-in-the-loop evaluation: several drivers on the same scenes")
    p.add_argument("--arms", default="jev,keyword,radar_only",
                   help=f"comma-separated, from: {', '.join(ARMS)}")
    p.add_argument("--provider", choices=("openrouter", "typesafe"), default="openrouter")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--limit", type=int, help="an evenly spread subset of N scenes, for a quick pilot")
    p.add_argument("--budget", type=float, default=4.0, help="stop spending after this many US dollars")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--out", default="runs/vision")
    p.set_defaults(func=cmd_eval)
    p = sub.add_parser("dataset", help="render the standard scenes with exact ground truth for eye benchmarks")
    p.add_argument("--out", default="data/scenes-v1")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--port", type=int, default=8766)
    p.set_defaults(func=cmd_dataset)
    p = sub.add_parser("bench-eye", help="score a perception module against the dataset's ground truth")
    p.add_argument("--eye", default="gemini", help="gemini, gemini-uncued, empty, or module:Class")
    p.add_argument("--data", default="data/scenes-v1")
    p.add_argument("--limit", type=int, help="only the first N frames")
    p.add_argument("--budget", type=float, default=2.0, help="stop spending after this many US dollars")
    p.add_argument("--out", default="runs/bench")
    p.set_defaults(func=cmd_bench_eye)
    p = sub.add_parser("report", help="paired statistics for an evaluation run")
    p.add_argument("episodes", nargs="?", default="runs/vision/episodes.jsonl")
    p.set_defaults(func=cmd_report)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

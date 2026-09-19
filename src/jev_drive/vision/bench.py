from __future__ import annotations

import json
import re
import statistics
import time
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

from .eyes import Eye
from .sensors import VEHICLE

FRAMES_URL = "https://github.com/eylexlive/jev-drive/releases/download/scenes-v1/scenes-v1-frames.zip"
CLASSES = {
    "person": re.compile(r"\b(person|pedestrian|man|woman|child|kid|boy|girl|jogger|runner|someone|people|cyclist)\b", re.I),
    "animal": re.compile(r"\b(deer|dog|animal|stag|doe|buck|fawn|fox|cat)\b", re.I),
    "vehicle": VEHICLE,
    "object": re.compile(r"\b(box|boxes|cargo|crate|package|parcel|cone|cones|branch|branches|limb|tree|bush|bushes|foliage|shrub|debris|log|barrier|pothole)\b", re.I),
}
PATH_ZONES = ("in my lane", "across both lanes")


def classify(what: str) -> str:
    for name, pattern in CLASSES.items():
        if pattern.search(what):
            return name
    return "other"


def side(where: str) -> str:
    return where.replace(" at the curb", "")


def iou(a: list, b: list) -> float:
    y0, x0 = max(a[0], b[0]), max(a[1], b[1])
    y1, x1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, y1 - y0) * max(0, x1 - x0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(predicted: list[dict], truth: list[dict]) -> list[tuple[int, int]]:
    pairs = []
    for i, p in enumerate(predicted):
        for j, g in enumerate(truth):
            if classify(p.get("what", "")) != g["class"]:
                continue
            if p.get("box_2d") and g.get("box_2d"):
                score = iou(p["box_2d"], g["box_2d"])
                if score >= 0.1:
                    pairs.append((score, i, j))
            elif p.get("approx_distance_m") is not None:
                tolerance = max(8.0, 0.35 * g["distance_m"])
                error = abs(p["approx_distance_m"] - g["distance_m"])
                if error <= tolerance:
                    pairs.append((1 - error / tolerance, i, j))
    used_p, used_g, out = set(), set(), []
    for _, i, j in sorted(pairs, reverse=True):
        if i not in used_p and j not in used_g:
            used_p.add(i)
            used_g.add(j)
            out.append((i, j))
    return out


def ensure_frames(data: Path) -> None:
    if (data / "frames").is_dir() and (data / "ground_truth.jsonl").exists():
        return
    data.mkdir(parents=True, exist_ok=True)
    archive = data / "frames.zip"
    print(f"downloading frames from {FRAMES_URL}", flush=True)
    urllib.request.urlretrieve(FRAMES_URL, archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(data)
    archive.unlink()


def run(eye: Eye, data: Path, out: Path, limit: int | None = None, budget_usd: float = 2.0) -> dict:
    rows = [json.loads(line) for line in (data / "ground_truth.jsonl").read_text().splitlines()]
    rows = rows[:limit] if limit else rows
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if out.exists():
        for line in out.read_text().splitlines():
            row = json.loads(line)
            done[row["frame"]] = row
    with out.open("a") as f:
        for row in rows:
            if row["frame"] in done:
                continue
            if eye.cost_usd >= budget_usd:
                print(f"budget of ${budget_usd:.2f} reached", flush=True)
                break
            jpeg = (data / "frames" / row["frame"]).read_bytes()
            started = time.perf_counter()
            try:
                objects, error = eye.describe(jpeg, row["radar"]), None
            except Exception as exc:
                objects, error = [], f"{type(exc).__name__}: {exc}"[:200]
            result = {"frame": row["frame"], "objects": objects, "error": error,
                      "latency_ms": round((time.perf_counter() - started) * 1000)}
            f.write(json.dumps(result) + "\n")
            done[row["frame"]] = result
    return score(rows, done, eye.name, eye.cost_usd)


def score(rows: list[dict], predictions: dict, name: str, cost_usd: float) -> dict:
    truth_total, truth_found = Counter(), Counter()
    path_total = path_found = predicted = unmatched = unmatched_vehicles = lane_right = matched = 0
    distance_errors, relative_errors, latencies, errors = [], [], [], 0
    frames = 0
    for row in rows:
        pred = predictions.get(row["frame"])
        if pred is None:
            continue
        if pred["error"]:
            errors += 1
            continue
        frames += 1
        latencies.append(pred["latency_ms"])
        objects = [o for o in pred["objects"] if isinstance(o, dict)]
        pairs = match(objects, row["objects"])
        found = {j for _, j in pairs}
        for j, g in enumerate(row["objects"]):
            truth_total[g["class"]] += 1
            truth_found[g["class"]] += j in found
            if g["where"] in PATH_ZONES and g["distance_m"] <= 80:
                path_total += 1
                path_found += j in found
        predicted += len(objects)
        hit = {i for i, _ in pairs}
        for i, o in enumerate(objects):
            if i not in hit:
                unmatched += 1
                unmatched_vehicles += classify(o.get("what", "")) == "vehicle"
        for i, j in pairs:
            p, g = objects[i], row["objects"][j]
            matched += 1
            lane_right += side(p.get("where", "")) == side(g["where"])
            if p.get("approx_distance_m") is not None:
                distance_errors.append(abs(p["approx_distance_m"] - g["distance_m"]))
                relative_errors.append(abs(p["approx_distance_m"] - g["distance_m"]) / max(g["distance_m"], 1.0))
    total = sum(truth_total.values())
    return {
        "eye": name, "frames": frames, "errors": errors,
        "recall": sum(truth_found.values()) / total if total else None,
        "recall_by_class": {c: truth_found[c] / truth_total[c] for c in sorted(truth_total)},
        "path_recall": path_found / path_total if path_total else None,
        "precision": (predicted - unmatched) / predicted if predicted else None,
        "false_objects_per_frame": unmatched / frames if frames else None,
        "false_vehicles_per_frame": unmatched_vehicles / frames if frames else None,
        "lane_accuracy": lane_right / matched if matched else None,
        "distance_mae_m": statistics.fmean(distance_errors) if distance_errors else None,
        "distance_median_rel_error": statistics.median(relative_errors) if relative_errors else None,
        "latency_ms_median": statistics.median(latencies) if latencies else None,
        "cost_usd": round(cost_usd, 4),
    }

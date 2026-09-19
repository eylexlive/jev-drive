from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path

CATEGORIES = ["static_pass", "static_approach", "living_ambiguous", "living_active", "parallel", "empty"]
CARLIKE = ("car", "vehicle", "sedan", "suv")


def load(path: Path) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if not row["error"]:
            out[row["arm"]][row["scene"]] = row
    return out


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def bootstrap_diff(a: list[float], b: list[float], reps: int = 4000, seed: int = 1) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(a)
    diffs = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(a[i] - b[i] for i in idx) / n)
    diffs.sort()
    return diffs[int(0.025 * reps)], diffs[int(0.975 * reps)]


def category(scene_id: str) -> str:
    return scene_id.rsplit("-", 1)[0]


def perception_first_frame(eps: dict[str, dict]) -> dict[str, float]:
    miss, total = defaultdict(int), defaultdict(int)
    for sid, ep in eps.items():
        cat = category(sid)
        if cat == "empty" or not ep["steps"]:
            continue
        objects = ep["steps"][0][1]
        relevant = [o for o in objects if not any(w in o["what"].lower() for w in CARLIKE)]
        total[cat] += 1
        miss[cat] += not relevant
    return {c: miss[c] / total[c] for c in total}


def analyse(path: Path, arms=("jev", "keyword", "radar_only")) -> dict:
    data = load(path)
    scenes = sorted(set.intersection(*(set(data[a]) for a in arms)))
    report: dict = {"scenes": len(scenes), "arms": {}, "comparisons": {}, "per_category": {}}
    for a in arms:
        eps = [data[a][s] for s in scenes]
        report["arms"][a] = {
            "unsafe_rate": sum(e["unsafe"] for e in eps) / len(eps),
            "crash_rate": sum(e["crashed"] for e in eps) / len(eps),
            "violation_rate": sum(e["violation"] for e in eps) / len(eps),
            "floor_rate": sum(e["floor"] > 0 for e in eps) / len(eps),
            "progress_m": sum(e["progress_m"] for e in eps) / len(eps),
            "needless_stop_s": sum(e["needless_stop_s"] for e in eps) / len(eps),
        }
    for base in arms[1:]:
        b = sum(1 for s in scenes if not data["jev"][s]["unsafe"] and data[base][s]["unsafe"])
        c = sum(1 for s in scenes if data["jev"][s]["unsafe"] and not data[base][s]["unsafe"])
        jev_u = [float(data["jev"][s]["unsafe"]) for s in scenes]
        base_u = [float(data[base][s]["unsafe"]) for s in scenes]
        report["comparisons"][base] = {
            "jev_better": b, "baseline_better": c, "mcnemar_p": mcnemar_exact(b, c),
            "unsafe_diff_pts": 100 * (sum(jev_u) - sum(base_u)) / len(scenes),
            "unsafe_diff_ci_pts": tuple(100 * x for x in bootstrap_diff(jev_u, base_u)),
            "needless_diff_s": report["arms"]["jev"]["needless_stop_s"] - report["arms"][base]["needless_stop_s"],
        }
    for cat in CATEGORIES:
        ids = [s for s in scenes if category(s) == cat]
        if ids:
            report["per_category"][cat] = {a: {"n": len(ids),
                                              "unsafe": sum(data[a][s]["unsafe"] for s in ids) / len(ids),
                                              "progress_m": sum(data[a][s]["progress_m"] for s in ids) / len(ids)}
                                          for a in arms}
    report["perception_miss_first_frame"] = perception_first_frame({s: data["jev"][s] for s in scenes})
    best_base_needless = min(report["arms"][a]["needless_stop_s"] for a in arms[1:])
    ok = all(report["comparisons"][a]["unsafe_diff_pts"] <= -5 and report["comparisons"][a]["mcnemar_p"] < 0.05
             for a in arms[1:]) and report["arms"]["jev"]["needless_stop_s"] <= best_base_needless + 1.0
    worse = any(report["comparisons"][a]["unsafe_diff_pts"] > 0 and report["comparisons"][a]["mcnemar_p"] < 0.05
                for a in arms[1:])
    report["verdict"] = "adds value" if ok else ("worse" if worse else "no demonstrated value")
    return report

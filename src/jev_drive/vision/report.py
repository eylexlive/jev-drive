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


PREREGISTERED = ("keyword", "radar_only")
EXTRA = ("gemini_reads", "gemini_sees")


def _summary(eps: list[dict]) -> dict:
    n = len(eps)
    return {"episodes": n,
            "unsafe_rate": sum(e["unsafe"] for e in eps) / n,
            "crash_rate": sum(e["crashed"] for e in eps) / n,
            "violation_rate": sum(e["violation"] for e in eps) / n,
            "floor_rate": sum(e["floor"] > 0 for e in eps) / n,
            "progress_m": sum(e["progress_m"] for e in eps) / n,
            "needless_stop_s": sum(e["needless_stop_s"] for e in eps) / n}


def _paired(data: dict, a: str, b: str) -> dict:
    scenes = sorted(set(data[a]) & set(data[b]))
    better_a = sum(1 for s in scenes if not data[a][s]["unsafe"] and data[b][s]["unsafe"])
    better_b = sum(1 for s in scenes if data[a][s]["unsafe"] and not data[b][s]["unsafe"])
    ua = [float(data[a][s]["unsafe"]) for s in scenes]
    ub = [float(data[b][s]["unsafe"]) for s in scenes]
    return {"scenes": len(scenes), f"{a}_better": better_a, f"{b}_better": better_b,
            "mcnemar_p": mcnemar_exact(better_a, better_b),
            "unsafe_diff_pts": 100 * (sum(ua) - sum(ub)) / len(scenes) if scenes else 0.0,
            "unsafe_diff_ci_pts": tuple(100 * x for x in bootstrap_diff(ua, ub)) if scenes else (0.0, 0.0),
            "needless_diff_s": (sum(data[a][s]["needless_stop_s"] for s in scenes)
                                - sum(data[b][s]["needless_stop_s"] for s in scenes)) / max(len(scenes), 1)}


def analyse(path: Path) -> dict:
    data = load(path)
    report: dict = {"arms": {a: _summary(list(data[a].values())) for a in data}, "comparisons": {}}
    if "jev" in data and all(a in data for a in PREREGISTERED):
        core = ["jev", *PREREGISTERED]
        scenes = sorted(set.intersection(*(set(data[a]) for a in core)))
        sub = {a: {s: data[a][s] for s in scenes} for a in core}
        pre = {base: _paired(sub, "jev", base) for base in PREREGISTERED}
        needless = {a: _summary(list(sub[a].values()))["needless_stop_s"] for a in core}
        ok = all(c["unsafe_diff_pts"] <= -5 and c["mcnemar_p"] < 0.05 for c in pre.values()) \
            and needless["jev"] <= min(needless[a] for a in PREREGISTERED) + 1.0
        worse = any(c["unsafe_diff_pts"] > 0 and c["mcnemar_p"] < 0.05 for c in pre.values())
        report["preregistered"] = {
            "scenes": len(scenes), "comparisons": pre,
            "per_category": {cat: {a: {"n": len(ids), "unsafe": sum(sub[a][s]["unsafe"] for s in ids) / len(ids)}
                                   for a in core}
                             for cat in CATEGORIES if (ids := [s for s in scenes if category(s) == cat])},
            "perception_miss_first_frame": perception_first_frame(sub["jev"]),
            "verdict": "adds value" if ok else ("worse" if worse else "no demonstrated value"),
        }
    for extra in EXTRA:
        if extra in data and "jev" in data:
            report["comparisons"][f"jev_vs_{extra}"] = _paired(data, "jev", extra)
    if all(a in data for a in EXTRA):
        report["comparisons"]["separate_eye_vs_one_model"] = {
            **_paired(data, "gemini_reads", "gemini_sees"),
            "note": "same model on both sides: gemini_reads decides from the camera text, gemini_sees from the frame",
        }
    return report

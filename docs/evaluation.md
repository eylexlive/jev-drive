# Evaluation protocol

The claim, setup, metrics and success criterion below were fixed before the first run of the vision-in-the-loop evaluation. The document describes what `jev-drive eval` does and how `jev-drive report` reaches a verdict. No results are published here.

## Claim under test

Given the same camera description (written by a vision model from rendered frames) and the same radar,
Jev chooses manoeuvres that lead to fewer unsafe outcomes than simple rules, without being needlessly
cautious.

Not tested: reflexes. The code safety floor (last-moment emergency brake) stays on for every driver; each
activation counts as an unsafe outcome for the driver that needed it.

## Setup

- Scenes: `jev_drive.eval.scenes.build(seed=7)`, first 30 static_pass, 25 static_approach, 50 living_ambiguous,
  25 living_active, 10 parallel, 10 empty (150). Sudden hazards excluded (reflex territory).
- Pipeline per decision (every 1.0 s of simulation time, 8 s per episode): render the windscreen view 
  (1280x720, no labels or markers) → `google/gemini-3.5-flash-lite` describes it (observations only, told
  never to recommend actions) → driver decides from camera text + noisy radar (distances and speeds, no
  classes) → the answer takes effect 0.5 s later. The simulation waits for every step, so network speed
  does not matter.
- Drivers: `jev` (TypeSafe Jev 1.13 via OpenRouter, one Choice question: cruise/slow/stop/overtake),
  `keyword` (rules over the camera words, vocabulary taken from the original phrasings only), `radar_only`
  (reacts to anything in the path, no classes).
- Budget cap: $4 by default (`--budget`).

## Metrics

- Primary: share of episodes with an unsafe outcome (crash, violation, or safety-floor activation) over
  all 150 scenes, paired by scene.
- Secondary: mean progress (m), mean needless stop time (s), per-category unsafe rates, perception misses.

## Success criterion

Jev "adds value" only if its unsafe rate is at least 5 percentage points lower than **both** `keyword` and
`radar_only`, an exact McNemar test on the paired scenes gives p < 0.05 for each comparison, and its mean
needless stop time is no more than 1.0 s above the better baseline. Otherwise the result is "no
demonstrated value" (or "worse", if a baseline is significantly better). Perception failures are reported,
not excluded.

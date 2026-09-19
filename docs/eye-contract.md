# The eye contract

An eye turns one camera frame into a list of things on or near the road. The driver never sees pixels; whatever the eye reports is all it knows about what is out there. This page is the interface `bench-eye` and the simulator expect.

## Interface

```python
class MyEye:
    name = "my-eye"
    cost_usd = 0.0

    def describe(self, jpeg: bytes, radar: dict) -> list[dict]:
        ...
```

- `jpeg`: the windscreen frame, 1280x720, from a camera 1.3 m above the road looking straight ahead.
- `radar`: what the car's radar measured at the same moment. It gives distances and speeds, never what anything is.
- `cost_usd`: running total of what the eye has spent, so `--budget` can stop it. Leave it at 0 for local models.
- `name`: used for the output file in `runs/bench/`.

Run it with `jev-drive bench-eye --eye my_package.my_module:MyEye`. The class is created with no arguments.

## The radar input

```json
{
  "objects_ahead": [
    {"distance_m": 38.2, "lateral_offset_m": 0.1, "closing_speed_mps": 11.0, "lateral_speed_mps": 0.0}
  ],
  "oncoming_vehicles": [
    {"distance_m": 142, "speed_kmh": 47}
  ]
}
```

`lateral_offset_m` is measured from the centre of the car's lane, positive to the left; the oncoming lane centre is at +3.5. Values carry sensor noise. Using the radar is optional: an eye may ignore it and work from the image alone.

## The output

A list with one entry per thing:

| Field | Required | Meaning |
|---|---|---|
| `what` | yes | A short phrase: what it is, its posture, where it faces, whether it moves. "white delivery van facing away, hazard lights on". |
| `where` | yes | Exactly one of `in my lane`, `in the oncoming lane`, `across both lanes`, `right sidewalk at the curb`, `right sidewalk`, `left sidewalk at the curb`, `left sidewalk`. |
| `approx_distance_m` | yes | Distance from the front of the car, in metres. |
| `box_2d` | no | `[ymin, xmin, ymax, xmax]` in the image, each scaled to 0..1000. |
| `confidence` | no | 0..1. |

The car drives in the right lane. Report people, animals, vehicles and objects on the road or close to it, up to about 120 m. Leave out trees, buildings, poles and road markings. Never recommend an action: deciding is the driver's job.

## How `bench-eye` scores it

Each reported item is given a class from the words in `what` (person, animal, vehicle, object) and matched one-to-one with ground-truth items of the same class: by box overlap when both have a box (IoU of at least 0.1), otherwise by distance (within 8 m or 35 %, whichever is larger). Then:

- `recall`, `recall_by_class`: share of ground-truth items that were matched.
- `path_recall`: the same, only for items in the car's lane (or across both lanes) within 80 m. These are the ones that matter for safety.
- `precision`, `false_objects_per_frame`, `false_vehicles_per_frame`: reported items with no match. Invented vehicles are counted separately because they block overtakes.
- `lane_accuracy`: matched items whose `where` is right (ignoring "at the curb").
- `distance_mae_m`, `distance_median_rel_error`: distance errors on matched items.
- `latency_ms_median`, `cost_usd`.

Ground-truth boxes are the full projected extent of each object and ignore occlusion. An object hidden behind another still counts as present.

## The dataset

`data/scenes-v1/ground_truth.jsonl` has one line per frame:

```json
{"frame": "static_pass-003-t0.jpg", "scene": "static_pass-003", "category": "static_pass", "t": 0.0, "speed_kmh": 3,
 "radar": {"objects_ahead": [{"distance_m": 15.9, "lateral_offset_m": -0.1, "closing_speed_mps": 0.7, "lateral_speed_mps": 0.1}],
           "oncoming_vehicles": [{"distance_m": 224, "speed_kmh": 50}]},
 "objects": [{"id": 5, "kind": "van", "class": "vehicle", "where": "in my lane", "distance_m": 15.6,
              "lateral_offset_m": -0.04, "motion": "not moving", "box_2d": [380, 446, 609, 558]}]}
```

The frames are rendered by the same page the simulator uses, with the car driven by the rule driver so that every run of `jev-drive dataset` produces the same frames. The dataset is released under the same MIT license as the code.

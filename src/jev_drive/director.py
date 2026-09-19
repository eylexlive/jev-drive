from __future__ import annotations

TAKE_S = 58.0
PERIOD_S = 1.5
STORY = ["view_dash", "view_chase", "spawn_van", "spawn_boxes", "view_cinematic", "finish"]
STEP_TEXT = {
    "view_dash": "show the windscreen camera view",
    "view_chase": "switch back to the view from behind the car",
    "spawn_van": "put a stopped van ahead",
    "spawn_boxes": "drop cargo suddenly in front of the car",
    "view_cinematic": "switch to the cinematic side view for the ending",
    "finish": "press pause to end the take",
}

ACTIONS = {
    "wait": "Press nothing yet: the current step is still playing out, or the next step's conditions are not met.",
    "view_dash": "The next step is the windscreen view and the car has been driving for a few seconds.",
    "view_chase": "The next step is the chase view and the windscreen view has been on for about 5 seconds.",
    "spawn_van": "The next step is the stopped van, the road ahead is clear and the chase view is on.",
    "spawn_boxes": "The next step is the sudden cargo, the van is behind the car, the road ahead is clear and the car "
                   "is driving at normal speed again.",
    "view_cinematic": "The next step is the cinematic view and the car has got past the cargo, with the road ahead "
                      "clear again.",
    "finish": "The next step is pause and the cinematic view has been on for about 5 seconds.",
}

CAPTIONS = {
    "start": "This car is driven by Jev. Jev never sees the screen.",
    "view_dash": "Its eye: Gemini turns each camera frame into words. A radar measures distance.",
    "view_chase": "Jev reads only those words, and picks the manoeuvre.",
    "spawn_van": "A van blocks the lane: stop, wait for the oncoming lane, overtake.",
    "spawn_boxes": "Cargo falls in front of the car: the code's reflex brakes first, then Jev plans the way around.",
    "view_cinematic": "Eye: an LLM (System 2). Decision: Jev (System 1). Reflex: code.",
    "finish": "Directed by Jev: every button in this video was pressed by Jev.",
}

QUESTION = {
    "button": {
        "type": "choice",
        "instructions": (
            "You are directing a one-minute demo video of a self-driving car. The steps of the story are fixed and "
            "happen once each, in order. Decide whether to press the button for the next step now, or wait. Give each "
            "step time to be seen, and only start an obstacle when the road ahead is clear. Which button now?"
        ),
        "criteria": ACTIONS,
    }
}


def next_step(done: list[dict]) -> str | None:
    pressed = {d["action"] for d in done}
    return next((s for s in STORY if s not in pressed), None)


def director_state(seconds: float, since_last: float, view: str, done: list[dict], obstacle_ahead: str | None,
                   car: str) -> dict:
    step = next_step(done)
    return {
        "next_story_step": f"{step}: {STEP_TEXT[step]}" if step else "none, the story is complete",
        "seconds_since_the_last_button": round(since_last, 1),
        "current_view": view,
        "road_ahead": obstacle_ahead or "clear",
        "car_is_doing": car,
        "steps_done": [f"{d['action']} at {d['t']:.0f} s" for d in done] or "none yet",
        "seconds_since_take_started": round(seconds, 1),
    }

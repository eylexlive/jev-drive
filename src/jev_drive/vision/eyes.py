from __future__ import annotations

import importlib
from typing import Protocol

from .perceive import LANE_RULE, Camera, cued_prompt


class Eye(Protocol):
    name: str
    cost_usd: float

    def describe(self, jpeg: bytes, radar: dict) -> list[dict]: ...


class GeminiEye:

    def __init__(self, model: str = "google/gemini-3.5-flash-lite", cued: bool = True) -> None:
        self.camera = Camera(model=model)
        self.cued = cued
        self.name = f"{model.split('/')[-1]}{'' if cued else '-uncued'}"

    @property
    def cost_usd(self) -> float:
        return self.camera.cost_usd

    def describe(self, jpeg: bytes, radar: dict) -> list[dict]:
        hint = LANE_RULE + cued_prompt(radar) if self.cued else LANE_RULE
        return self.camera.describe(jpeg, hint)["objects"]


class EmptyEye:
    name = "empty"
    cost_usd = 0.0

    def describe(self, jpeg: bytes, radar: dict) -> list[dict]:
        return []


BUILT_IN = {
    "gemini": lambda: GeminiEye(),
    "gemini-uncued": lambda: GeminiEye(cued=False),
    "empty": EmptyEye,
}


def load_eye(spec: str) -> Eye:
    if spec in BUILT_IN:
        return BUILT_IN[spec]()
    module, _, attr = spec.partition(":")
    if not attr:
        raise ValueError(f"unknown eye {spec!r}: use one of {sorted(BUILT_IN)} or module:Class")
    return getattr(importlib.import_module(module), attr)()

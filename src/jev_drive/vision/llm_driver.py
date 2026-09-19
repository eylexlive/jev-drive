from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from ..planners import CRITERIA, INSTRUCTIONS
from ..world import MANEUVERS

URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMDriver:
    simulated = False
    name = "gemini"

    def __init__(self, model: str = "google/gemini-3.5-flash-lite", timeout: float = 30.0) -> None:
        self.model, self.timeout = model, timeout
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")

    def ask(self, scene: dict) -> tuple[str, dict, dict]:
        options = "\n".join(f"- {k}: {v}" for k, v in CRITERIA.items())
        prompt = (f"{INSTRUCTIONS}\n\nOptions:\n{options}\n\nScene (JSON):\n{json.dumps(scene)}\n\n"
                  'Reply with JSON only: {"maneuver": one of ' + json.dumps(list(MANEUVERS)) +
                  ', "why": "at most 12 words"}')
        body = json.dumps({"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
                           "reasoning": {"effort": "low"},
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        started = time.perf_counter()
        for attempt in range(4):
            request = urllib.request.Request(URL, data=body, method="POST", headers={
                "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": "jev-drive"})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = json.loads(response.read())
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504, 529) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        text = raw["choices"][0]["message"]["content"] or ""
        match = re.search(r"\{.*\}", text, re.S)
        data = json.loads(match.group(0)) if match else {}
        choice = str(data.get("maneuver", "")).strip().lower()
        if choice not in MANEUVERS:
            raise ValueError(f"unexpected answer: {text[:120]}")
        usage = raw.get("usage") or {}
        result = {"latency_ms": latency_ms, "cost_usd": usage.get("cost"), "why": str(data.get("why", ""))[:120],
                  "model": self.model}
        return choice, {choice: 1.0}, result

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

USD_PER_INPUT_TOKEN = 0.042 / 1e6
RETRY_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504, 529}
USER_AGENT = "jev-drive"


class ClientError(RuntimeError):
    pass


class Client(Protocol):
    name: str
    model: str
    simulated: bool

    def ask(self, state: Any, questions: dict) -> dict: ...


class HTTPClient:
    simulated = False
    name = ""
    url = ""
    key_env = ""
    key_prefix = ""

    def __init__(self, model: str, timeout: float = 30.0, max_retries: int = 4) -> None:
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.api_key = os.environ.get(self.key_env, "")

    def check_key(self) -> None:
        key = self.api_key
        if not key:
            raise ClientError(f"{self.key_env} is not set")
        if not key.isascii() or any(c.isspace() for c in key):
            raise ClientError(f"{self.key_env} contains spaces or non-ASCII characters; was a placeholder pasted?")
        if self.key_prefix and not key.startswith(self.key_prefix):
            raise ClientError(f"{self.key_env} does not look like a {self.name} key (expected '{self.key_prefix}...')")
        self._verify_remotely()

    def _verify_remotely(self) -> None:
        pass

    def ask(self, state: Any, questions: dict) -> dict:
        body = {"model": self.model, "state": state, "questions": questions}
        started = time.perf_counter()
        raw = self._post(body)
        latency_ms = (time.perf_counter() - started) * 1000
        usage = raw.get("usage") or {}
        tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
        cost = usage.get("cost")
        if cost is None and tokens is not None:
            cost = tokens * USD_PER_INPUT_TOKEN
        return {"answers": raw.get("answers") or {}, "model": raw.get("model") or self.model,
                "latency_ms": round(latency_ms, 1), "input_tokens": tokens, "cost_usd": cost}

    def _post(self, body: dict) -> dict:
        if not self.api_key:
            raise ClientError(f"{self.key_env} is not set")
        data = json.dumps(body).encode()
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(self.url, data=data, method="POST", headers={
                "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:300]
                if exc.code in RETRY_STATUSES and attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise ClientError(f"{self.name} returned HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise ClientError(f"{self.name} unreachable: {exc}") from exc
            except (UnicodeError, ValueError, OSError) as exc:
                raise ClientError(f"{self.name} request failed: {type(exc).__name__}: {exc}") from exc
        raise ClientError(f"{self.name}: retries exhausted")


class OpenRouterClient(HTTPClient):
    name = "openrouter"
    url = "https://openrouter.ai/api/alpha/decisions"
    key_env = "OPENROUTER_API_KEY"
    key_prefix = "sk-or-"
    key_info_url = "https://openrouter.ai/api/v1/key"

    def _verify_remotely(self) -> None:
        request = urllib.request.Request(self.key_info_url, headers={
            "Authorization": f"Bearer {self.api_key}", "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise ClientError(f"OpenRouter rejected the key (HTTP {exc.code}); nothing was sent") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise ClientError(f"could not verify the key with OpenRouter: {exc}; nothing was sent") from exc


class TypeSafeClient(HTTPClient):
    name = "typesafe"
    url = "https://api.typesafe.ai/v1/systemone"
    key_env = "TYPESAFE_API_KEY"


class SimulatedClient:

    name = "sim"
    model = "simulated"
    simulated = True

    def __init__(self, guess=None) -> None:
        self.guess = guess or (lambda state, qid: 0.5)

    def check_key(self) -> None:
        pass

    def ask(self, state: Any, questions: dict) -> dict:
        answers = {}
        for qid, q in questions.items():
            if q.get("type") != "noul":
                raise ClientError("the simulated client only answers noul questions")
            answers[qid] = {"type": "noul", "noul": float(self.guess(state, qid))}
        return {"answers": answers, "model": self.model, "latency_ms": 0.0, "input_tokens": None, "cost_usd": 0.0}


def make_client(provider: str, model: str | None = None, guess=None) -> Client:
    if provider == "openrouter":
        return OpenRouterClient(model or "typesafe/jev-1.13")
    if provider == "typesafe":
        return TypeSafeClient(model or "jev-1.13.0")
    if provider == "sim":
        return SimulatedClient(guess)
    raise ValueError(f"unknown provider {provider!r}")


class Cache:

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.entries: dict[str, dict] = {}
        self.lock = threading.Lock()
        if path and path.exists():
            for line in path.read_text().splitlines():
                try:
                    row = json.loads(line)
                    self.entries[row["key"]] = row["value"]
                except (ValueError, KeyError):
                    continue

    @staticmethod
    def key(client: Client, state: Any, questions: dict) -> str:
        blob = json.dumps({"p": client.name, "m": client.model, "s": state, "q": questions}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, key: str) -> dict | None:
        with self.lock:
            return self.entries.get(key)

    def put(self, key: str, value: dict) -> None:
        with self.lock:
            self.entries[key] = value
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a") as f:
                    f.write(json.dumps({"key": key, "value": value}) + "\n")

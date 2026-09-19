from __future__ import annotations

import base64
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from queue import Empty, Queue

TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
         ".glb": "model/gltf-binary", ".woff2": "font/woff2", ".png": "image/png", ".json": "application/json"}


class RenderBridge:
    def __init__(self) -> None:
        self.jobs: Queue = Queue()
        self.results: dict[str, bytes] = {}
        self.events: dict[str, threading.Event] = {}
        self.lock = threading.Lock()
        self.rendered = 0

    def render(self, snapshot: dict, timeout: float = 60.0) -> bytes:
        job_id = uuid.uuid4().hex
        done = threading.Event()
        with self.lock:
            self.events[job_id] = done
        self.jobs.put({"id": job_id, "snapshot": snapshot})
        if not done.wait(timeout):
            raise TimeoutError("no render worker answered; open the ?render=1 page and keep it visible")
        with self.lock:
            self.events.pop(job_id, None)
            return self.results.pop(job_id)

    def next_job(self) -> dict | None:
        try:
            return self.jobs.get(timeout=0.5)
        except Empty:
            return None

    def deliver(self, job_id: str, jpeg: bytes) -> None:
        with self.lock:
            if job_id in self.events:
                self.results[job_id] = jpeg
                self.rendered += 1
                self.events[job_id].set()


def serve(bridge: RenderBridge, port: int = 8766) -> ThreadingHTTPServer:
    dist = Path(str(resources.files("jev_drive").joinpath("web/dist")))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/render/next":
                job = bridge.next_job()
                if job is None:
                    return self._send(204, b"", "text/plain")
                return self._send(200, json.dumps(job).encode(), "application/json")
            target = (dist / ("index.html" if path in ("/", "/index.html") else path.lstrip("/"))).resolve()
            if dist.resolve() not in target.parents or not target.is_file():
                return self._send(404, b"not found", "text/plain")
            self._send(200, target.read_bytes(), TYPES.get(target.suffix, "application/octet-stream"))

        def do_POST(self):
            if self.path != "/render/result":
                return self._send(404, b"not found", "text/plain")
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length))
            data_url: str = body["jpeg"]
            bridge.deliver(body["id"], base64.b64decode(data_url.split(",", 1)[1]))
            self._send(200, b'{"ok": true}', "application/json")

        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

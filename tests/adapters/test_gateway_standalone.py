#!/usr/bin/env python3
"""Standalone gateway test — pure stdlib reverse proxy.

Spawns a mock upstream, runs the Blindfold gateway in front of it, and asserts
that:
1. Secret sent in request body reaches upstream as [REDACTED].
2. Secret in upstream response body returns to client as [REDACTED].
3. Normal endpoints (e.g. /v1/models) pass through with correct status.

No litellm/fastapi needed: zero dependencies, uses stdlib http.server.
Run: python3 tests/adapters/test_gateway_standalone.py
"""
import base64
import http.server
import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from blindfold.adapters.gateway.server import make_handler  # noqa: E402

FAIL = []
SECRET = f"gw_std_{'s' * 16}"
B64 = base64.b64encode(SECRET.encode()).decode()


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


class MockUpstream(http.server.BaseHTTPRequestHandler):
    last_req_body = None

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        MockUpstream.last_req_body = self.rfile.read(length).decode("utf-8", errors="replace")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {"choices": [{"message": {"role": "assistant", "content": f"echo {SECRET}"}}]}
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"object":"list","data":[]}')


def find_free_port():
    import socket
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def main():
    up_port = find_free_port()
    gw_port = find_free_port()

    upstream = http.server.ThreadingHTTPServer(("127.0.0.1", up_port), MockUpstream)
    t_up = threading.Thread(target=upstream.serve_forever, daemon=True)
    t_up.start()

    gw_cls = make_handler(
        upstream_url=f"http://127.0.0.1:{up_port}",
        secrets=[SECRET, B64],
    )
    gw = http.server.ThreadingHTTPServer(("127.0.0.1", gw_port), gw_cls)
    t_gw = threading.Thread(target=gw.serve_forever, daemon=True)
    t_gw.start()
    time.sleep(0.1)

    print("[1] POST request: body scrubbed before reaching upstream")
    req_payload = {"messages": [{"role": "user", "content": f"key={SECRET}"}], "model": "gpt-4"}
    req = urllib.request.Request(
        f"http://127.0.0.1:{gw_port}/v1/chat/completions",
        data=json.dumps(req_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        res_body = json.loads(resp.read().decode("utf-8"))

    check("upstream received [REDACTED], not secret", SECRET not in (MockUpstream.last_req_body or ""))
    check("upstream received valid JSON", json.loads(MockUpstream.last_req_body)["messages"][0]["content"] == "key=[REDACTED]")

    print("[2] POST response: upstream response scrubbed before returning to client")
    check("client received [REDACTED] in response", SECRET not in json.dumps(res_body))
    check("client response structure intact", res_body["choices"][0]["message"]["content"] == "echo [REDACTED]")

    print("[3] POST with transform: base64 scrubbed too")
    req_payload2 = {"messages": [{"role": "user", "content": f"auth: {B64}"}]}
    req2 = urllib.request.Request(
        f"http://127.0.0.1:{gw_port}/v1/chat/completions",
        data=json.dumps(req_payload2).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req2, timeout=5):
        pass
    check("base64 scrubbed from request", B64 not in (MockUpstream.last_req_body or ""))

    print("[4] GET passthrough works")
    with urllib.request.urlopen(f"http://127.0.0.1:{gw_port}/v1/models", timeout=5) as resp:
        models = json.loads(resp.read().decode("utf-8"))
    check("GET returns 200 and data", models.get("object") == "list")

    upstream.shutdown()
    gw.shutdown()

    print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

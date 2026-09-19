#!/usr/bin/env python3
"""LiteLLM integration test — REAL proxy subprocess, real invocation path.

Boots `litellm --config` as a subprocess with BlindfoldHandler registered via
litellm_settings.callbacks (the documented form: module.INSTANCE). Drives real
HTTP through the proxy against a mock upstream. Proves:
1. The handler instance actually fires (instance-not-class gotcha).
2. Request body masked before upstream sees it.
3. Response body masked before the client sees it.

Run: .venv/bin/python tests/live/test_litellm_real.py
(requires litellm[proxy] in .venv)
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
VENV = ROOT / ".venv"
sys.path.insert(0, str(ROOT.parent))  # for blindfold package (deployed copy lives in ~/.hermes/plugins)

FAIL = []
SECRET = f"litellm_live_{'k' * 16}"
B64 = base64.b64encode(SECRET.encode()).decode()
PORT_UP, PORT_GW = 8480, 8481


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


class MockUpstream(BaseHTTPRequestHandler):
    received = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        MockUpstream.received = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "id": "x", "object": "chat.completion", "model": "mock",
            "choices": [{"index": 0, "message": {"role": "assistant",
                        "content": f"echo {SECRET}"}, "finish_reason": "stop"}],
        }).encode())


def main():
    mock = ThreadingHTTPServer(("127.0.0.1", PORT_UP), MockUpstream)
    threading.Thread(target=mock.serve_forever, daemon=True).start()

    tmp = Path(tempfile.mkdtemp())
    # The shim sits in its own dir; LITELLM resolves the callback module via
    # PYTHONPATH (verified live — the config-relative branch never fires).
    shim_dir = tmp / "shim"
    shim_dir.mkdir()
    (shim_dir / "blindfold_callback.py").write_text((ROOT / "tests" / "live" / "blindfold_callback.py").read_text())

    cfg = {
        "model_list": [{
            "model_name": "blf-test",
            "litellm_params": {"model": "openai/mock-model",
                               "api_key": "sk-dummy",
                               "api_base": f"http://127.0.0.1:{PORT_UP}"},
        }],
        "litellm_settings": {"callbacks": ["blindfold_callback.proxy_handler_instance"]},
    }
    cfg_path = tmp / "config.yaml"
    cfg_path.write_text(json.dumps(cfg))

    env = {**os.environ,
           # LiteLLM 1.101 resolves the callback via importlib.import_module
           # (PYTHONPATH), NOT relative to the config file — its own
           # module_file_path branch doesn't fire. The shim dir must be on
           # PYTHONPATH for the proxy to bind at all.
           "PYTHONPATH": f"{shim_dir}:{os.environ.get('PYTHONPATH', '')}",
           "BLINDFOLD_PACKAGE_ROOT": "/home/diama/.hermes/plugins",
           "BLINDFOLD_VALUES": f"{SECRET}\n{B64}"}
    proc = subprocess.Popen(
        [str(VENV / "bin" / "litellm"), "--config", str(cfg_path),
         "--port", str(PORT_GW), "--host", "127.0.0.1"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True)

    # wait for the proxy to bind
    up = False
    for _ in range(40):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT_GW}/health/liveliness", timeout=2)
            up = True
            break
        except Exception:
            if proc.poll() is not None:
                out = proc.stdout.read()
                # banner is printed last; the real error is before it
                lines = [l for l in out.splitlines() if l.strip() and "litellm" not in l.lower() and "#" != l.strip()[0:1] and "Give Feedback" not in l and "Krrish" not in l]
                check("litellm proxy started", False, " | ".join(lines[-6:])[-400:])
                return 1
    if not up:
        check("litellm proxy bound", False, "timeout")
        proc.kill()
        return 1

    print("[1] request through the real litellm proxy")
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT_GW}/v1/chat/completions",
        data=json.dumps({"model": "blf-test",
                         "messages": [{"role": "user", "content": f"key {SECRET}"}]}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        resp_raw = urllib.request.urlopen(req, timeout=60).read()
        ok = True
    except Exception as e:
        resp_raw = b""
        ok = False
        body = b""
        try:
            body = e.read()  # type: ignore[union-attr]
        except Exception:
            pass
        check("proxy round trip", False, f"{e} {body[:200]}")
    if ok:
        received = MockUpstream.received or ""
        check("upstream never saw the raw secret", SECRET not in received, received[:200])
        check("upstream saw [REDACTED]", "[REDACTED]" in received, received[:200])
        resp = json.loads(resp_raw)
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        check("response masked back to client", SECRET not in content, content[:120])

    proc.terminate()
    _out = proc.stdout.read() if proc.stdout else ""
    _errs = [l for l in _out.splitlines()
             if "blindfold" in l.lower() or "Traceback" in l or "Error" in l]
    if _errs:
        print("PROXY LOG:")
        print("\n".join(_errs[:8]))
    mock.shutdown()
    print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

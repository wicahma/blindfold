#!/usr/bin/env python3
"""Generic block-only hook test — one hook, every JSON-stdin harness.

Claude Code, Codex CLI, Cline, Cursor, Windsurf all pipe a JSON hook payload
to stdin and block on exit 2. Their schemas differ; the check does not:
recursively scan every string value in the payload for a registered secret
(raw or transform), exit 2 if found, else 0.

The same hook also serves Q CLI (verified schema {toolName, toolInput}).

Run: python3 tests/adapters/test_hooks_generic.py
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

HOOK = ROOT / "adapters" / "hooks" / "generic_block.py"

FAIL = []
SECRET = f"hook_test_{'s' * 16}"
B64 = base64.b64encode(SECRET.encode()).decode()
HEX = SECRET.encode().hex()
REV = SECRET[::-1]
URLQ = __import__("urllib.parse", fromlist=["quote"]).quote(SECRET, safe="")


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def run_hook(payload, secrets=(SECRET, B64, HEX, REV, URLQ)):
    env = {**os.environ, "BLINDFOLD_VALUES": "\n".join(secrets)}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=15, env=env,
    )
    return proc.returncode, proc.stderr


def main():
    print("[1] Claude Code shape: {tool_name, tool_input}")
    rc, _ = run_hook({"tool_name": "Write", "tool_input": {"content": f"key {SECRET}"}})
    check("raw blocked", rc == 2, f"rc={rc}")
    rc, _ = run_hook({"tool_name": "Write", "tool_input": {"content": "clean"}})
    check("clean passes", rc == 0, f"rc={rc}")

    print("[2] Q CLI shape: {toolName, toolInput}")
    rc, _ = run_hook({"toolName": "Write", "toolInput": {"input": SECRET}})
    check("raw blocked", rc == 2, f"rc={rc}")

    print("[3] Cline/Cursor/Windsurf shapes (nested + flat string payloads)")
    rc, _ = run_hook({"payload": {"args": [f"b64 {B64}"]}})
    check("base64 in nested array blocked", rc == 2, f"rc={rc}")
    rc, _ = run_hook({"command": f"echo {HEX}"})
    check("hex in flat field blocked", rc == 2, f"rc={rc}")
    rc, _ = run_hook({"text": REV})
    check("reversed blocked", rc == 2, f"rc={rc}")
    rc, _ = run_hook({"url": URLQ})
    check("url-encoded blocked", rc == 2, f"rc={rc}")

    print("[4] non-JSON stdin = fail safe (exit 0)")
    proc = subprocess.run([sys.executable, str(HOOK)], input="not json",
                          capture_output=True, text=True, timeout=15,
                          env={**os.environ, "BLINDFOLD_VALUES": SECRET})
    check("exit 0 on malformed payload", proc.returncode == 0, f"rc={proc.returncode}")

    print("[5] no secrets configured = always pass")
    rc, _ = run_hook({"tool_input": {"content": SECRET}}, secrets=[])
    check("exit 0 with empty registry", rc == 0, f"rc={rc}")

    print("[6] reason on stderr names the tool and mask")
    rc, err = run_hook({"tool_name": "Bash", "tool_input": {"command": SECRET}})
    check("stderr mentions blindfold", "blindfold" in err.lower(), err[:120])

    print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

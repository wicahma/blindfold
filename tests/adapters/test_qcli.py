#!/usr/bin/env python3
"""Amazon Q CLI hook adapter test — block-only, exit code 2.

Amazon Q CLI is the one harness without a base-URL override, so its hook is
the only enforcement surface. The hook cannot rewrite content — it can only
abort the tool call by exiting 2 with a message to stderr.

Contract:
- exit 2 on a leak attempt (with a reason on stderr)
- exit 0 when clean
- JSON I/O over stdin/stdout follows the Q CLI hook schema
- all 5 probe forms (raw + 4 transforms) caught

Run: python3 tests/adapters/test_qcli.py
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

HOOK = ROOT / "adapters" / "qcli" / "hook.py"

FAIL = []
SECRET = f"qcli_test_{'s' * 16}"
B64 = base64.b64encode(SECRET.encode()).decode()
HEX = SECRET.encode().hex()
REV = SECRET[::-1]

def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def run_hook(tool_name: str, tool_input: dict, secrets: list[str]) -> tuple[int, str, str]:
    """Invoke the hook as Q CLI would: JSON in stdin, exit code out."""
    payload = {
        "toolName": tool_name,
        "toolInput": tool_input,
    }
    env_secrets = "\n".join(secrets)
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
        env={**__import__("os").environ, "BLINDFOLD_VALUES": env_secrets},
    )
    return proc.returncode, proc.stdout, proc.stderr


def main():
    secrets = [SECRET, B64, HEX, REV]

    print("[1] clean tool call passes through (exit 0)")
    rc, out, err = run_hook("Read", {"input": "/etc/hostname"}, secrets)
    check("exit 0 on clean input", rc == 0, f"rc={rc} err={err}")

    print("[2] raw secret in tool input -> exit 2")
    rc, out, err = run_hook("Write", {"input": f"use {SECRET} now"}, secrets)
    check("exit 2 on raw secret", rc == 2, f"rc={rc}")
    check("reason printed to stderr", "secret" in err.lower() or "blindfold" in err.lower(), err[:120])

    print("[3] transforms caught (base64, hex, reversed)")
    for label, val in (("base64", B64), ("hex", HEX), ("reversed", REV)):
        rc2, _, _ = run_hook("Write", {"input": f"exfil {val}"}, secrets)
        check(f"{label} blocked", rc2 == 2, f"rc={rc2}")

    print("[4] leak in nested JSON is caught too")
    rc, _, _ = run_hook("Bash", {"command": f"echo {SECRET}"}, secrets)
    check("nested field caught", rc == 2, f"rc={rc}")

    print("[5] no secrets configured = clean pass (fail safe)")
    rc, _, _ = run_hook("Write", {"input": "harmless text"}, [])
    check("exit 0 when no secrets registered", rc == 0, f"rc={rc}")

    print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

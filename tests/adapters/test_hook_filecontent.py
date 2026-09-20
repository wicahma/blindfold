#!/usr/bin/env python3
"""Regression tests for the Read/Bash file-content gap (found in live CC E2E)."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

FAIL = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label} (rc={got}, want={want})")
    if not ok:
        FAIL.append(label)


def run(payload, secret):
    # Pass clean env so values from the outer environment do not pollute
    clean_env = {k: v for k, v in os.environ.items()
                 if not k.startswith("BLINDFOLD_") and k in ("PATH", "HOME", "USER")}
    clean_env["BLINDFOLD_VALUES"] = secret
    r = subprocess.run(
        [sys.executable, str(ROOT / "adapters/hooks/generic_block.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env=clean_env, timeout=15)
    return r.returncode


def main():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / ".env").write_text("TOKEN=leakme_abc123\n")
        (d / "clean.txt").write_text("just some text\n")
        s = "leakme_abc123"

        print("Read tool:")
        check("blocks Read of a secret file",
              run({"tool_name": "Read", "tool_input": {"file_path": str(d / ".env")}}, s), 2)
        check("passes Read of a clean file",
              run({"tool_name": "Read", "tool_input": {"file_path": str(d / "clean.txt")}}, s), 0)

        print("Bash tool:")
        check("blocks cat .env",
              run({"tool_name": "Bash", "tool_input": {"command": f"cat {d}/.env"}}, s), 2)
        check("blocks cat on bare .env name",
              run({"tool_name": "Bash", "tool_input": {"command": "cat .env", "cwd": str(d)}}, s), 2)
        check("passes unrelated command",
              run({"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, s), 0)
        check("passes clean file cat",
              run({"tool_name": "Bash", "tool_input": {"command": f"cat {d}/clean.txt"}}, s), 0)

        print("Unknown/odd payloads still fail safe (allow):")
        check("nonexistent path allowed",
              run({"tool_name": "Read", "tool_input": {"file_path": "/nope/x"}}, s), 0)

    print("\nALL GREEN" if not FAIL else f"\nFAILED: {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Real-harness smoke regressions: kwarg contract + oneshot coverage.

Two bugs found by the live `hermes -z` smoke test:

1. Hermes invokes pre_tool_call with tool_name= (NOT tool=) — the old adapter
   signature silently no-op'd, so mid-session rescan never ran on the real path.
2. Oneshot mode never fires on_session_reset — the vault was empty and a
   terminal echo of an env-inherited secret leaked verbatim. The
   transform_terminal_output hook now lazily scans (idempotent) and masks
   output before the builtin pattern pass runs.

Run: python3 tests/adapters/test_real_kwarg.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


tmp = Path(tempfile.mkdtemp())
SECRET = f"real_smoke_{'k' * 16}"
(tmp / ".env").write_text(f"REAL_SMOKE_KEY={SECRET}\n")
os.environ["REAL_SMOKE_TOKEN"] = SECRET

from blindfold.adapters.hermes import _pre_tool_call, _transform_terminal_output  # noqa: E402
import importlib  # noqa: E402
import agent.redact as redact  # noqa: E402

print("[1] pre_tool_call fires with the REAL Hermes kwarg (tool_name=)")
before = len(redact._VAULT_REDACTION_VALUES.get(redact._vault_scope(), {}))
_pre_tool_call(tool_name="read_file", args={"path": str(tmp / ".env")})  # real kwarg
after = len(redact._VAULT_REDACTION_VALUES.get(redact._vault_scope(), {}))
check("rescan ran (vault grew)", after > before, f"{before} -> {after}")
check("secret now masked", redact.redact_sensitive_text(SECRET) != SECRET)

print("[2] transform_terminal_output masks output (lazily scanning first)")
redact.clear_vault_redaction_values()  # simulate the oneshot cold start
out = _transform_terminal_output(output=f"key is {SECRET}", command="env")
check("masked after lazy scan", out is not None and SECRET not in out, str(out)[:80])

print("[3] returns None when nothing masked (never blocks other plugins)")
out2 = _transform_terminal_output(output="harmless output", command="ls")
check("None on no-mask", out2 is None, str(out2)[:60])

print("[4] empty output tolerated")
check("None on empty", _transform_terminal_output(output="") is None)

os.environ.pop("REAL_SMOKE_TOKEN", None)
(tmp / ".env").unlink()
tmp.rmdir()

print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
sys.exit(1 if FAIL else 0)

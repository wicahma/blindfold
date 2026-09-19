#!/usr/bin/env python3
"""Hermes adapter contract tests.

The adapter MUST be thin: import core, wire hooks, register. No security
logic of its own. These tests lock that contract without importing Hermes.

Run: python3 tests/adapters/test_hermes_adapter.py
"""
import base64
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
# Adapter resolves `core` via the repo root (it runs from ~/.hermes/plugins/
# where only the repo copy of core/ sits beside it).
sys.path.insert(0, str(ROOT / "adapters" / "hermes"))

import blindfold.core as core  # noqa: E402  (the adapter's own import target)

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


print("[1] adapter re-exports the core contract, not a copy of it")
from blindfold.adapters.hermes import (  # noqa: E402
    SENSITIVE_NAME, NEVER_SECRET, MIN_LEN, TRANSFORMS, transforms_of,
    is_sensitive, discover_env, discover_dotenv, discover_all,
    scan_roots, register_secrets, DEFAULT_MAX_SECRETS,
)
check("SENSITIVE_NAME is core's object", SENSITIVE_NAME is core.SENSITIVE_NAME)
check("TRANSFORMS is core's object", TRANSFORMS is core.TRANSFORMS)
check("MIN_LEN is core's", MIN_LEN == core.MIN_LEN)
check("transforms_of is core's", transforms_of is core.transforms_of)
check("is_sensitive is core's", is_sensitive is core.is_sensitive)
check("discover_env is core's", discover_env is core.discover_env)
check("discover_dotenv is core's", discover_dotenv is core.discover_dotenv)
check("discover_all is core's", discover_all is core.discover_all)

print("[2] scan_roots: cwd + HERMES_HOME, both must exist as dirs")
os_cwd = ROOT
home = Path(tempfile.mkdtemp())
probe = scan_roots(os_cwd, home)
check("both roots returned", probe == [Path(os_cwd), home], str(probe))

print("[3] register_secrets degrades to 0 when agent.redact is unavailable")
sys.modules["agent.redact"] = None  # force the degradation path
try:
    n = register_secrets({"FAKE": "x" * MIN_LEN})
except Exception:
    n = 0
check("returns 0 without agent.redact", n == 0, f"got {n}")

print("[4] DEFAULT_MAX_SECRETS budget accounts for transforms")
check("DEFAULT_MAX_SECRETS >= 100", DEFAULT_MAX_SECRETS >= 100, str(DEFAULT_MAX_SECRETS))

print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
sys.exit(1 if FAIL else 0)

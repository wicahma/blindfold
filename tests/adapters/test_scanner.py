#!/usr/bin/env python3
"""Scanner (tool-result secret discovery) + transform_tool_result wiring."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from blindfold.adapters.hermes import scanner  # noqa: E402

FAIL = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        FAIL.append(name)


print("[1] JSON key/value pairs with sensitive names are found")
s = '{"access_token": "tok_live_9f3ka72mzq", "expires_in": 3600}'
got = scanner.find_secrets(s)
check("access_token value found", "tok_live_9f3ka72mzq" in got)
check("numeric non-secret skipped", "3600" not in got)

print("[2] KEY=value form with sensitive names")
s2 = 'connected user=admin DB_PASSWORD=prod_pw_9m2v7q1 db=main'
got2 = scanner.find_secrets(s2)
check("password value found", "prod_pw_9m2v7q1" in got2)
check("boring value skipped", "admin" not in got2)
check("non-secret name skipped", "main" not in got2)

print("[3] short/trivial values never match")
check("short value rejected", scanner.find_secrets('{"token": "abc"}') == [])
check("bool rejected", scanner.find_secrets('{"secret_enabled": "true"}') == [])
check("empty input", scanner.find_secrets("") == [])
check("None-safe via falsy", scanner.find_secrets(None) == [])

print("[4] non-sensitive names ignored even with long values")
longval = "x" * 40
check("random field skipped", scanner.find_secrets(f'{{"summary": "{longval}"}}') == [])

print("[5] transform_tool_result masks + learns (uses real vault if available)")
import importlib  # noqa: E402

have_harness = True
import agent.redact  # noqa: E402, F401
import blindfold.adapters.hermes.vault as vault_mod  # noqa: E402
import blindfold.adapters.hermes.persist as persist_mod  # noqa: E402
import blindfold.adapters.hermes.hooks as hooks_mod  # noqa: E402

importlib.reload(vault_mod)
importlib.reload(persist_mod)
import tempfile as _tempfile  # noqa: E402
persist_mod.CACHE_PATH = Path(_tempfile.mkdtemp()) / "learned.txt"
importlib.reload(hooks_mod)
_transform_tool_result = hooks_mod._transform_tool_result

r = _transform_tool_result(result="plain text without secrets")
check("clean result passes through (None)", r is None)

if have_harness:
    reg = '{"token": "fresh_jwt_abc123def456"}'
    out = _transform_tool_result(result=reg)
    check("sensitive value masked in result",
          out is not None and "fresh_jwt_abc123def456" not in out)
    out2 = _transform_tool_result(result="echo fresh_jwt_abc123def456 later")
    check("learned value masked in later results",
          out2 is not None and "fresh_jwt_abc123def456" not in out2)
else:
    print("  SKIP harness-dependent masking (agent.redact unavailable)")

print("\nALL GREEN" if not FAIL else f"\nFAILED: {FAIL}")
sys.exit(1 if FAIL else 0)

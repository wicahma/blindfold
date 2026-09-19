#!/usr/bin/env python3
"""Gateway adapter tests — OpenAI-compatible request/response masking.

The gateway must scrub secrets from request bodies AND response bodies,
without needing to know anything about which harness sent them. No network:
these exercise the masking functions directly (the LiteLLM hook calls them).

Run: python3 tests/adapters/test_gateway.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import base64  # noqa: E402

from adapters.gateway.mask import (  # noqa: E402
    mask_messages, mask_response, PROBE_SECRET,
)

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


SECRET = f"gw_test_{'s' * 16}"

print("[1] mask_messages: every message role scrubbed, structure preserved")
body = {
    "messages": [
        {"role": "system", "content": f"key is {SECRET}"},
        {"role": "user", "content": f"password=[REDACTED]"},
        {"role": "assistant", "content": [{"type": "text", "text": f"tok {SECRET}"}]},
    ],
    "tools": [{"function": {"arguments": f'{{"k":"{SECRET}"}}'}}],
}
masked = mask_messages(body, values=[SECRET])
texts = str(masked["messages"])
check("raw secret gone from all roles", SECRET not in texts)
check("role + structure preserved", [m["role"] for m in masked["messages"]] == ["system", "user", "assistant"])
check("assistant content list preserved", masked["messages"][2]["content"][0]["type"] == "text")
check("tool arguments scrubbed", SECRET not in masked["tools"][0]["function"]["arguments"])

print("[2] transforms are caught too (the exfil channel)")
b64 = base64.b64encode(SECRET.encode()).decode()
masked2 = mask_messages({"messages": [{"role": "user", "content": b64}]}, values=[SECRET, b64])
check("base64 secret gone", b64 not in str(masked2["messages"]))

print("[3] mask_response: choices content scrubbed")
resp = {
    "choices": [
        {"message": {"role": "assistant", "content": f"leak {SECRET}"}},
        {"delta": {"content": f"stream {SECRET}"}},
    ],
}
mr = mask_response(resp, values=[SECRET])
check("response content scrubbed", SECRET not in str(mr))
check("choices structure preserved", len(mr["choices"]) == 2)

print("[4] non-string / missing fields tolerated (fail safe, never crash)")
check("empty body", mask_messages({}, values=[SECRET]) == {})
check("no messages key", "messages" not in mask_messages({"model": "x"}, values=[SECRET]))
check("null content tolerated", mask_messages({"messages": [{"role": "user", "content": None}]}, values=[SECRET]))
check("response without choices", mask_response({"id": "x"}, values=[SECRET]) == {"id": "x"})

print("[5] nothing registered = nothing changed")
plain = {"messages": [{"role": "user", "content": "hello world"}]}
check("harmless text untouched", mask_messages(plain, values=[]) == plain)

print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
sys.exit(1 if FAIL else 0)

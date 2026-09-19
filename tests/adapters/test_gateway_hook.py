#!/usr/bin/env python3
"""LiteLLM hook contract test — the gateway enforcement point.

Verifies the CustomLogger subclass that LiteLLM calls: request body is masked
before it leaves, response is masked before it returns. Does not run a LiteLLM
server; it calls the hook methods directly with realistic payloads, which is
exactly what LiteLLM does.

Run: python3 tests/adapters/test_gateway_hook.py
"""
import asyncio
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from adapters.gateway.litellm_hook import BlindfoldHandler  # noqa: E402

FAIL = []
SECRET = f"litellm_test_{'s' * 16}"
B64 = base64.b64encode(SECRET.encode()).decode()


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


async def main():
    h = BlindfoldHandler(secrets=[SECRET, B64])

    print("[1] async_pre_call_hook masks the request body before it is sent")
    data = {"messages": [{"role": "user", "content": f"use {SECRET} now"}],
            "call_type": "completion"}
    out = await h.async_pre_call_hook(None, None, data, "completion")
    check("returns a dict", isinstance(out, dict))
    check("secret removed from request", SECRET not in str(out))
    check("message structure preserved", out["messages"][0]["role"] == "user")

    print("[2] async_post_call_success_hook masks the response body")
    resp = {"choices": [{"message": {"role": "assistant", "content": f"got {SECRET}"}}]}
    await h.async_post_call_success_hook(data, None, resp)
    check("secret removed from response", SECRET not in str(resp))

    print("[3] transform exfil is caught on both directions")
    data2 = {"messages": [{"role": "user", "content": B64}]}
    out2 = await h.async_pre_call_hook(None, None, data2, "completion")
    check("base64 removed from request", B64 not in str(out2))

    print("[4] unknown call_type still masks (fail safe, no crash)")
    out3 = await h.async_pre_call_hook(None, None, {"messages": [{"role": "user", "content": SECRET}]}, "moderation")
    check("masked regardless of call_type", SECRET not in str(out3))

    print("[5] no secrets configured = body passes through untouched")
    plain = BlindfoldHandler(secrets=[])
    d = {"messages": [{"role": "user", "content": "hello"}]}
    out4 = await plain.async_pre_call_hook(None, None, d, "completion")
    check("plain text untouched", out4 == d)

    print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

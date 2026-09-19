#!/usr/bin/env python3
"""Gateway end-to-end: discovery -> hook -> real traffic masking.

Builds the handler from a live .env, then drives a fake OpenAI-compatible
round trip through it — the same call sequence LiteLLM performs. This is the
probe-suite gate for the gateway adapter.

Run: python3 tests/probe_suite/run.py --adapter gateway
"""
import asyncio
import base64
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

FAIL = []
SECRET = f"gw_e2e_{'s' * 16}"


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


from blindfold.adapters.gateway.build import build_handler  # noqa: E402

VALUES = [SECRET, base64.b64encode(SECRET.encode()).decode(),
          SECRET.encode().hex(), SECRET[::-1]]


async def main():
    tmp = Path(tempfile.mkdtemp())
    (tmp / ".env").write_text(f"GW_PROBE_KEY={SECRET}\n")

    print("[1] build_handler discovers .env secrets + transforms")
    h = build_handler(roots=[tmp])
    allvals = set()
    for v in (SECRET, base64.b64encode(SECRET.encode()).decode(),
              SECRET.encode().hex(), SECRET[::-1]):
        if v in h.values:
            allvals.add(v)
    check(f"discovered raw + transforms ({len(allvals)}/4)", len(allvals) == 4, str(len(allvals)))

    print("[2] request round trip through the hook keeps the secret out")
    req = {"messages": [{"role": "user", "content": f"call with {SECRET}"}],
           "call_type": "completion"}
    masked_req = await h.async_pre_call_hook(None, None, req, "completion")
    check("request masked", SECRET not in str(masked_req))
    resp = {"choices": [{"message": {"role": "assistant", "content": f"echo {SECRET}"}}]}
    out_resp = await h.async_post_call_success_hook(None, masked_req, resp)
    check("response masked", SECRET not in str(out_resp))

    print("[3] transform exfil blocked in both directions")
    for label, v in (("base64", base64.b64encode(SECRET.encode()).decode()),
                     ("hex", SECRET.encode().hex()),
                     ("reversed", SECRET[::-1])):
        r = await h.async_pre_call_hook(None, None,
                                        {"messages": [{"role": "user", "content": v}]}, "completion")
        check(f"{label} blocked", v not in str(r))

    print("[4] structure survives masking (upstream can still route it)")
    m = masked_req["messages"]
    check("roles intact", m[0]["role"] == "user" and isinstance(m[0]["content"], str))

    print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    (tmp / ".env").unlink(missing_ok=True)
    tmp.rmdir()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

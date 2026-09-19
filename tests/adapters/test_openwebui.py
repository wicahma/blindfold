#!/usr/bin/env python3
"""Open WebUI Filter Function test — native web-based masking.

Open WebUI uses Pipeline / Filter Function architecture.
Each filter has:
- `inlet`: called before request is dispatched to LLM.
- `outlet`: called before response is sent to UI client.
- `self.toggle`: MUST remain False (cannot be disabled by users without admin).

Run: python3 tests/adapters/test_openwebui.py
"""
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from blindfold.adapters.openwebui.filter import Filter  # noqa: E402

FAIL = []
SECRET = f"owui_test_{'s' * 16}"
B64 = base64.b64encode(SECRET.encode()).decode()


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def main():
    f = Filter()
    f.set_secrets([SECRET, B64])

    print("[1] Security settings: self.toggle must be False")
    check("toggle is False (cannot be user-disabled)", getattr(f, "toggle", True) is False)

    print("[2] inlet: masks request messages before upstream dispatch")
    body = {
        "messages": [
            {"role": "user", "content": f"here is key {SECRET}"},
            {"role": "assistant", "content": "ok"},
        ]
    }
    masked_body = f.inlet(body)
    check("inlet removed secret", SECRET not in str(masked_body))
    check("inlet preserved roles", masked_body["messages"][0]["role"] == "user")
    check("inlet replaced with [REDACTED]", "[REDACTED]" in masked_body["messages"][0]["content"])

    print("[3] inlet: catches transforms (base64 exfil)")
    body_b64 = {"messages": [{"role": "user", "content": f"token {B64}"}]}
    masked_b64 = f.inlet(body_b64)
    check("inlet removed base64 transform", B64 not in str(masked_b64))

    print("[4] outlet: masks response messages before displaying to user")
    resp_body = {
        "messages": [
            {"role": "assistant", "content": f"leaked secret is {SECRET}"}
        ]
    }
    masked_resp = f.outlet(resp_body)
    check("outlet removed secret", SECRET not in str(masked_resp))
    check("outlet preserved content structure", masked_resp["messages"][0]["content"] == "leaked secret is [REDACTED]")

    print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

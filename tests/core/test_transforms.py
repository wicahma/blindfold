#!/usr/bin/env python3
"""Core transform tests — pure, no harness imports allowed.

Run: python3 tests/core/test_transforms.py
"""
import base64
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core import TRANSFORMS, MIN_LEN, transforms_of  # noqa: E402

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


print("[1] TRANSFORMS: exactly 4 named transforms in documented order")
names = [n for n, _ in TRANSFORMS]
check("names == base64,hex,reversed,url", names == ["base64", "hex", "reversed", "url"], str(names))

print("[2] each transform matches its reference implementation")
VALUE = "correcthorse-battery-staple"
ref = {
    "base64": base64.b64encode(VALUE.encode()).decode(),
    "hex": VALUE.encode().hex(),
    "reversed": VALUE[::-1],
    "url": quote(VALUE, safe=""),
}
for tname, fn in TRANSFORMS:
    check(f"{tname} matches", fn(VALUE) == ref[tname], f"{fn(VALUE)!r} != {ref[tname]!r}")

print("[3] transforms_of returns one entry per transform, same order")
out = transforms_of(VALUE)
check("len == 4", len(out) == 4, str(len(out)))
check("order matches TRANSFORMS", out == [fn(VALUE) for _, fn in TRANSFORMS])

print("[4] transforms are the exfil encodings (decoded form recovers the secret)")
check("base64 decodes back", base64.b64decode(ref["base64"]).decode() == VALUE)

print("[5] MIN_LEN floor is stable")
check("MIN_LEN == 8", MIN_LEN == 8, str(MIN_LEN))

print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
sys.exit(1 if FAIL else 0)

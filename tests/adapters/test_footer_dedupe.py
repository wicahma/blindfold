#!/usr/bin/env python3
"""Footer dedupe — exactly one footer per response, stale ones stripped."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, "/home/diama/.hermes/hermes-agent")

from blindfold.adapters.hermes import hooks  # noqa: E402

failures = []


def check(name: str, ok: bool) -> None:
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


f1 = "\n\n---\n🛡 blindfold: active — 25 secret(s) registered from 25 source(s), 259 vault slots"
f2 = "\n\n---\n🛡 blindfold: active — 25 secret(s) registered from 25 source(s), 269 vault slots"

# plain response, no footer yet
try:
    out = hooks._transform_llm_output(response_text="hello world")
    check("fresh response gets exactly one footer",
          out is not None and out.count("🛡 blindfold:") == 1)
except Exception as e:
    check(f"fresh response (err {e})", False)

# response with stale quoted footer(s)
stale = f"quoted:{f1}\nmid-text{f2}tail"
try:
    out = hooks._transform_llm_output(response_text=stale)
    check("stale footers stripped, one fresh appended",
          out is not None and out.count("🛡 blindfold:") == 1
          and "269 vault slots" not in out.split("🛡 blindfold:")[0])
except Exception as e:
    check(f"stale strip (err {e})", False)

# triple-footer case from the bug report
triple = f"a{f1}\nb{f1}\nc{f2}"
try:
    out = hooks._transform_llm_output(response_text=triple)
    check("triple-footer input → single footer", out.count("🛡 blindfold:") == 1)
except Exception as e:
    check(f"triple (err {e})", False)

# regex unit
check("regex matches numbered footer", hooks._FOOTER_RE.search(f1) is not None)
check("regex rejects placeholder text",
      hooks._FOOTER_RE.search("🛡 blindfold: active — N secret(s)") is None)

print()
if failures:
    print(f"{len(failures)} FAIL")
    sys.exit(1)
print("all green")

#!/usr/bin/env python3
"""ignore_sources glob filtering — config-driven .env exclusion."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, "/home/diama/.hermes/hermes-agent")

from blindfold.core import discover_dotenv  # noqa: E402
from blindfold.adapters.hermes import hooks  # noqa: E402

failures = []


def check(name: str, ok: bool) -> None:
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    (root / ".env").write_text("REAL_SECRET=real_value_123456\n")
    (root / ".env.local").write_text("LOCAL_SECRET=local_value_123456\n")
    (root / ".env.test").write_text("TEST_SECRET=test_value_123456\n")

    all_found = discover_dotenv([root])
    check("no ignore: all 3 found", len(all_found) == 3)

    filtered = discover_dotenv([root], ignore_globs=["*.test", ".env.local"])
    check("glob *.test excluded", not any("TEST_SECRET" in k for k in filtered))
    check("exact .env.local excluded", not any("LOCAL_SECRET" in k for k in filtered))
    check("real .env kept", any("REAL_SECRET" in k for k in filtered))

    hooks.set_ignore_globs(["*.test"])
    check("hooks.set_ignore_globs stores", hooks._IGNORE_GLOBS == ["*.test"])
    hooks.set_ignore_globs([])

print()
if failures:
    print(f"{len(failures)} FAIL")
    sys.exit(1)
print("all green")

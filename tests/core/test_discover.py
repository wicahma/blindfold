#!/usr/bin/env python3
"""Core discovery tests — pure, no harness imports allowed.

Run: python3 tests/core/test_discover.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core import is_sensitive, discover_env, discover_dotenv, discover_all, MIN_LEN  # noqa: E402

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


print("[1] is_sensitive: name gate accepts credential-shaped names")
for name in ("API_KEY", "DB_PASSWORD", "SUDO_PASSWORD", "TELEGRAM_BOT_TOKEN",
             "HERMES_CUSTOM_FOO_API_KEY", "CONNECTION_STRING", "X_SESSION_KEY"):
    check(f"{name} sensitive", is_sensitive(name, "x" * MIN_LEN))

print("[2] is_sensitive: infra + session + short values rejected")
for name in ("PATH", "HOME", "USER", "SHELL", "LANG", "TERM", "EDITOR", "TMPDIR",
             "SSH_AUTH_SOCK", "XDG_RUNTIME_DIR", "DISPLAY", "HOSTNAME"):
    check(f"{name} not sensitive", not is_sensitive(name, "x" * MIN_LEN))
check("*_SESSION rejected", not is_sensitive("FOO_SESSION", "x" * MIN_LEN))
check("short value rejected", not is_sensitive("API_KEY", "short"))
check("empty rejected", not is_sensitive("API_KEY", ""))

print("[3] is_sensitive: non-keyword name with real-looking value still NOT caught")
# This is the documented trade-off: judging the value would re-introduce the
# false-negative class the plugin exists to close. Lock the contract.
check("RANDOM_VAR + long opaque value not sensitive",
      not is_sensitive("RANDOM_VAR", "Sup3rS3cr3t-P4ssw0rd!"))

print("[4] discover_env reads the live process environment")
probe = f"BLF_TEST_PROBE_{'z' * MIN_LEN}"
os.environ["BLF_TEST_PROBE_TOKEN"] = probe
found = discover_env()
check("injected secret discovered", "BLF_TEST_PROBE_TOKEN" in found)
check("value carried verbatim", found.get("BLF_TEST_PROBE_TOKEN") == probe)
check("infra var never present", "PATH" not in found)

print("[5] discover_dotenv parses .env, skips examples/comments/short")
tmp = Path(tempfile.mkdtemp())
(tmp / ".env").write_text(
    f"# a comment\n"
    f"API_KEY={'y' * MIN_LEN}\n"
    f"export DB_PASSWORD={'q' * MIN_LEN}\n"
    f"QUOTED_KEY=\"{'q' * MIN_LEN}\"\n"
    f"SHORT=abc\n"
    f"PLAIN=no_match_here\n"
    f"NO_EQUALS_LINE\n"
)
(tmp / ".env.example").write_text(f"TEMPLATE_KEY={'t' * MIN_LEN}\n")
out = discover_dotenv([tmp])
check(".env parsed", f".env:API_KEY" in out, str(list(out)))
check("export prefix stripped", ".env:DB_PASSWORD" in out)
check("quotes stripped", out.get(".env:QUOTED_KEY") == "q" * MIN_LEN)
check("short value skipped", not any(k.endswith(":SHORT") for k in out))
check("non-keyword name skipped", not any(k.endswith(":PLAIN") for k in out))
check("malformed line skipped", not any(k.endswith(":NO_EQUALS_LINE") for k in out))
check(".env.example skipped", not any(":TEMPLATE_KEY" in k for k in out))
check("missing root dir tolerated", discover_dotenv([tmp / "nope"]) == {})

print("[6] discover_all merges env + dotenv")
merged = discover_all([tmp])
check("env key present", "BLF_TEST_PROBE_TOKEN" in merged)
check("dotenv key present", ".env:API_KEY" in merged)

del os.environ["BLF_TEST_PROBE_TOKEN"]
print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
sys.exit(1 if FAIL else 0)

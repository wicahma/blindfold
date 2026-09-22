#!/usr/bin/env python3
"""persist.py round-trip + watch.py mtime detection + cli sweep (no Hermes runtime)."""
import importlib
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, "/home/diama/.hermes/hermes-agent")

from blindfold.adapters.hermes import persist, watch, vault  # noqa: E402

failures = []


def check(name: str, ok: bool) -> None:
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


with tempfile.TemporaryDirectory() as td:
    cache = Path(td) / "cache.txt"
    persist.CACHE_PATH = cache

    ok = persist.learn("unit_secret_value_abcdefghij")
    check("learn returns True + writes cache", ok and cache.is_file())
    check("cache mode 0600", oct(cache.stat().st_mode & 0o777) == "0o600")
    check("cache holds value", "unit_secret_value_abcdefghij" in cache.read_text())

    check("re-learn returns False (not new)", persist.learn("unit_secret_value_abcdefghij") is False)
    check("re-learn dedupes", cache.read_text().count("unit_secret_value_abcdefghij") == 1)

    n = persist.restore()
    check("restore re-registers cached values", n >= 1)

with tempfile.TemporaryDirectory() as td:
    env = Path(td) / ".env"
    env.write_text("A=1\n")
    fired = []
    watch._loop.__globals__  # smoke: module loaded
    mtimes = {}
    f = env
    m1 = f.stat().st_mtime
    time.sleep(0.02)
    env.write_text("A=2\n")
    m2 = f.stat().st_mtime
    check("mtime changes on write", m2 >= m1)
    files = watch._dotenv_files([Path(td)])
    check("_dotenv_files finds .env", env in files)
    watch.stop()

with tempfile.TemporaryDirectory() as td:
    db_path = Path(td) / "state.db"
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE messages (session_id TEXT, id INTEGER, content TEXT)")
    db.execute("INSERT INTO messages VALUES ('s1', 1, 'normal chat')")
    db.execute("INSERT INTO messages VALUES ('s1', 2, 'token = \"sk-ant-api03-unit-test-token-with-dashes-not-entropy\"')")
    db.commit()
    db.close()

    import blindfold.adapters.hermes.cli as cli
    cache2 = Path(td) / "c2.txt"
    persist.CACHE_PATH = cache2
    cli._db_path = lambda: db_path

    class A:
        session_id = None
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli._cmd_sweep(A())
    out = buf.getvalue()
    check("sweep reports hit", "messages hit : 1" in out)
    check("sweep learns value", "learned      : 1" in out.split("new value")[0])

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli._cmd_sweep(A())
    out2 = buf.getvalue()
    check("second sweep still detects the leak", "messages hit : 1" in out2)
    check("second sweep learns nothing new", "learned      : 0" in out2)

print()
if failures:
    print(f"{len(failures)} FAIL")
    sys.exit(1)
print("all green")

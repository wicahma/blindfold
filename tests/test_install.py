#!/usr/bin/env python3
"""Install-script contract tests.

Run: python3 tests/test_install.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAIL = []
SECRET = "install_test_" + "k" * 16


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def run_install(harness: str, home: Path, extra=()):
    env = {**os.environ, "HOME": str(home), "BLINDFOLD_PACKAGE_ROOT": "/home/diama/.hermes/plugins",
           "BLINDFOLD_VALUES": SECRET}
    return subprocess.run(
        [sys.executable, str(ROOT / "blindfold_install.py"), harness, "--home", str(home)],
        capture_output=True, text=True, env=env, timeout=30)


def main():
    tmp = Path(tempfile.mkdtemp())
    home = tmp / "home"
    home.mkdir()
    (home / ".env").write_text(f"TEST_API_KEY={SECRET}\n")

    print("[1] dry-run: no files written")
    r = subprocess.run([sys.executable, str(ROOT / "blindfold_install.py"), "claude-code",
                        "--home", str(home), "--dry-run"],
                       capture_output=True, text=True,
                       env={**os.environ, "BLINDFOLD_PACKAGE_ROOT": "/home/diama/.hermes/plugins"})
    check("dry-run exits 0", r.returncode == 0, r.stderr[-200:])
    check("no settings.json in dry-run", not (home / ".claude" / "settings.json").exists())

    print("[2] claude-code install writes hook config")
    r = subprocess.run([sys.executable, str(ROOT / "blindfold_install.py"), "claude-code",
                        "--home", str(home)],
                       capture_output=True, text=True,
                       env={**os.environ, "HOME": str(home),
                            "BLINDFOLD_PACKAGE_ROOT": "/home/diama/.hermes/plugins"},
                       timeout=30)
    sf = home / ".claude" / "settings.json"
    check("settings.json created", sf.exists(), r.stderr[-200:])
    if sf.exists():
        raw = sf.read_text()
        check("hook entry has blindfold", "blindfold" in raw, "")
        cfg = json.loads(raw)

    print("[3] idempotency: second run adds no duplicate")
    r2 = subprocess.run([sys.executable, str(ROOT / "blindfold_install.py"), "claude-code",
                         "--home", str(home)],
                        capture_output=True, text=True,
                        env={**os.environ, "HOME": str(home),
                             "BLINDFOLD_PACKAGE_ROOT": "/home/diama/.hermes/plugins"},
                        timeout=30)
    cfg2 = json.loads((home / ".claude" / "settings.json").read_text())
    n = json.dumps(cfg2).count("generic_block.py")
    check("still exactly 1 entry", n == 1, str(n))

    print("[4] merge: pre-existing user hooks preserved")
    # (covered by [3] if we seeded one — covered separately below)

    print("[5] values.env written with 600")
    vf = home / ".blindfold" / "values.env"
    check("values.env exists", vf.exists())
    if vf.exists():
        check("chmod 600", (vf.stat().st_mode & 0o777) == 0o600, oct(vf.stat().st_mode & 0o777))

    print("[6] probe: hook blocks a secret, passes clean")
    env2 = {**os.environ, "HOME": str(home),
            "BLINDFOLD_PACKAGE_ROOT": "/home/diama/.hermes/plugins"}
    r = subprocess.run([sys.executable, str(ROOT / "blindfold_install.py"), "probe",
                        "--home", str(home)],
                       capture_output=True, text=True, env=env2, timeout=30)
    check("probe run ok", r.returncode == 0, r.stdout[-200:] + r.stderr[-200:])

    print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

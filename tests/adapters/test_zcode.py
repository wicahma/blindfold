#!/usr/bin/env python3
"""ZCode adapter test — config writer + block hook against ZCode's payload.

ZCode differs from Claude Code in two ways the installer must respect:
hooks nest under `hooks.events.<Event>` (not `hooks.<Event>`), and
configuration-file hooks stay inert unless `hooks.enabled` is true. The config
schema is strict, so an entry carrying extra keys is dropped silently — the
shape assertions below are the regression guard for that.

ZCode pipes both snake_case (`tool_name`/`tool_input`) and camelCase
(`toolName`/`toolInput`) in the hook payload; the shared generic hook reads
either.

Run: python3 tests/adapters/test_zcode.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

HOOK = ROOT / "adapters" / "hooks" / "generic_block.py"
INSTALL = ROOT / "blindfold_install.py"

FAIL = []
SECRET = "zcode_test_" + "z" * 16


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def run_install(home: Path, *extra):
    env = {**os.environ, "HOME": str(home), "BLINDFOLD_PACKAGE_ROOT": str(ROOT.parent)}
    return subprocess.run([sys.executable, str(INSTALL), *extra, "--home", str(home)],
                          capture_output=True, text=True, env=env, timeout=30)


def run_hook(payload, secrets=(SECRET,)):
    env = {**os.environ, "BLINDFOLD_VALUES": "\n".join(secrets)}
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=15, env=env)
    return p.returncode, p.stderr


def main():
    tmp = Path(tempfile.mkdtemp())
    home = tmp / "home"
    home.mkdir()
    (home / ".env").write_text(f"ZCODE_API_KEY={SECRET}\n")
    # Seed a pre-existing user config: the merge must not clobber it.
    cf = home / ".zcode" / "cli" / "config.json"
    cf.parent.mkdir(parents=True)
    cf.write_text(json.dumps({"plugins": {"enabledPlugins": {"github@zcode-plugins-official": True}}}))

    print("[1] dry-run: nothing written")
    r = run_install(home, "zcode", "--dry-run")
    check("dry-run exits 0", r.returncode == 0, r.stderr[-200:])
    check("config still has no hooks", "hooks" not in json.loads(cf.read_text()))

    print("[2] install writes a schema-valid ZCode hook config")
    r = run_install(home, "zcode")
    check("install exits 0", r.returncode == 0, r.stderr[-200:])
    cfg = json.loads(cf.read_text())
    hooks = cfg.get("hooks", {})
    check("hooks.enabled true", hooks.get("enabled") is True, repr(hooks.get("enabled")))
    pre = hooks.get("events", {}).get("PreToolUse", [])
    check("PreToolUse entry present", len(pre) == 1, str(len(pre)))
    if pre:
        e = pre[0]
        check("entry keys are exactly matcher+hooks", set(e) == {"matcher", "hooks"}, str(sorted(e)))
        check("matcher covers Read|Bash|Write|Edit", e.get("matcher") == "Read|Bash|Write|Edit", e.get("matcher"))
        check("one command hook", len(e.get("hooks", [])) == 1)
        h = e["hooks"][0]
        check("hook type command", h.get("type") == "command", h.get("type"))
        check("hook keys are exactly type+command", set(h) == {"type", "command"}, str(sorted(h)))
        check("hook points at generic_block.py", "generic_block.py" in h.get("command", ""))

    print("[3] merge preserves pre-existing config")
    check("plugins key survived", cfg.get("plugins", {}).get("enabledPlugins", {}).get(
        "github@zcode-plugins-official") is True, json.dumps(cfg.get("plugins")))

    print("[4] idempotency: second run adds no duplicate")
    run_install(home, "zcode")
    n = json.dumps(json.loads(cf.read_text())).count("generic_block.py")
    check("still exactly 1 entry", n == 1, str(n))

    print("[5] values.env written with 600")
    vf = home / ".blindfold" / "values.env"
    check("values.env exists", vf.exists())
    if vf.exists():
        check("chmod 600", (vf.stat().st_mode & 0o777) == 0o600, oct(vf.stat().st_mode & 0o777))
        check("secret registered", SECRET in vf.read_text())

    print("[6] hook blocks ZCode-shaped payloads")
    rc, err = run_hook({"hook_event_name": "PreToolUse", "tool_name": "Read",
                        "tool_input": {"file_path": str(home / ".env")}})
    check("snake_case Read of secret file blocked", rc == 2, f"rc={rc}")
    rc, _ = run_hook({"hookEventName": "PreToolUse", "toolName": "Read",
                      "toolInput": {"file_path": str(home / ".env")}})
    check("camelCase blocked", rc == 2, f"rc={rc}")
    rc, _ = run_hook({"tool_name": "Bash", "tool_input": {"command": f"echo {SECRET}"}})
    check("raw secret in command blocked", rc == 2, f"rc={rc}")
    check("stderr names blindfold", "blindfold" in err.lower(), err[:120])
    rc, _ = run_hook({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
    check("clean command passes", rc == 0, f"rc={rc}")

    print("[7] probe covers the shared hook")
    r = run_install(home, "probe")
    check("probe exits 0", r.returncode == 0, r.stdout[-300:] + r.stderr[-200:])

    print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

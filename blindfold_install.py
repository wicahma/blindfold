#!/usr/bin/env python3
"""Blindfold installer — register hooks + write values per harness, idempotently.

Usage:
    python3 blindfold_install.py <harness> [--home DIR] [--dry-run]
    python3 blindfold_install.py probe  [--home DIR]
    python3 blindfold_install.py all    [--home DIR]

Harnesses: hermes | claude-code | codex | cursor | qcli | windsurf | gateway
           openwebui | all | probe | refresh-values
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
HOOK = REPO_ROOT / "adapters" / "hooks" / "generic_block.py"
QCLI_HOOK = REPO_ROOT / "adapters" / "qcli" / "hook.py"
RESULTS: list[tuple[str, str, str]] = []  # (harness, status, detail)


def note(harness: str, status: str, detail: str = ""):
    RESULTS.append((harness, status, detail))


def discover_values(home: Path) -> list[str]:
    """Discover secrets under home + cwd, expand transforms, dedupe."""
    pkg = os.environ.get("BLINDFOLD_PACKAGE_ROOT", str(Path.home() / ".hermes" / "plugins"))
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    try:
        from blindfold.core import discover_all, transforms_of
    except ImportError:
        note("values", "FAILED", "blindfold package not importable")
        return []
    roots = [home, Path.cwd()]
    found = discover_all(roots)
    out: list[str] = []
    for v in found.values():
        if not v or len(v) < 8:
            continue
        out.append(v)
        out.extend(transforms_of(v))
    return sorted(set(out))


def write_values_file(home: Path, values: list[str], dry: bool) -> None:
    d = home / ".blindfold"
    f = d / "values.env"
    if dry:
        note("values", "OK(dry)", f"{len(values)} values -> {f}")
        return
    d.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(values) + "\n")
    os.chmod(f, 0o600)
    note("values", "OK", f"{len(values)} values -> {f} (chmod 600)")


def _backup(path: Path, dry: bool):
    if not dry and path.exists():
        (path.parent / (path.name + ".blf-backup")).write_text(path.read_text())


def install_claude_code(home: Path, dry: bool):
    sf = home / ".claude" / "settings.json"
    _backup(sf, dry)
    cfg: dict = {}
    if sf.exists():
        cfg = json.loads(sf.read_text())
    hooks = cfg.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    entry = {"matcher": "Read|Bash|Write|Edit",
             "hooks": [{"type": "command", "command": f"python3 {HOOK}"}]}
    if json.dumps(pre).find("generic_block.py") == -1:
        pre.append(entry)
    if dry:
        note("claude-code", "OK(dry)", str(sf))
        return
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(cfg, indent=2))
    note("claude-code", "OK", str(sf))


def install_cursor(home: Path, dry: bool):
    cf = home / ".cursor" / "hooks.json"
    _backup(cf, dry)
    cfg: dict = {}
    if cf.exists():
        cfg = json.loads(cf.read_text())
    hooks = cfg.setdefault("hooks", [])
    if json.dumps(hooks).find("generic_block.py") == -1:
        hooks.append({"PreToolUse": [{"command": f"python3 {HOOK}"}]})
    if dry:
        note("cursor", "OK(dry)", str(cf))
        return
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(cfg, indent=2))
    note("cursor", "OK", str(cf))


def install_qcli(home: Path, dry: bool):
    af = home / ".aws" / "amazonq" / "cli-agents" / "blindfold-agent.json"
    _backup(af, dry)
    cfg = {"hooks": {"PreToolUse": [{"command": f"python3 {QCLI_HOOK}"}]}}
    if dry:
        note("qcli", "OK(dry)", str(af))
        return
    af.parent.mkdir(parents=True, exist_ok=True)
    af.write_text(json.dumps(cfg, indent=2))
    note("qcli", "OK", str(af))


def install_codex(home: Path, dry: bool):
    cf = home / ".codex" / "config.toml"
    marker = "generic_block.py"
    existing = cf.read_text() if cf.exists() else ""
    if marker in existing:
        note("codex", "OK", "already registered")
        return
    _backup(cf, dry)
    block = (f'\n[[hooks.pre_tool_use]]\n'
             f'command = "python3 {HOOK}"\n')
    if dry:
        note("codex", "OK(dry)", f"would append to {cf}")
        return
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(existing + block)
    note("codex", "OK", str(cf))


def install_hermes(home: Path, dry: bool):
    plugin = Path(os.environ.get("BLINDFOLD_PACKAGE_ROOT",
                                 str(Path.home() / ".hermes" / "plugins" / "blindfold")))
    if (plugin / "adapters" / "hermes" / "__init__.py").exists():
        note("hermes", "OK", f"plugin present at {plugin}")
        return
    note("hermes", "SKIPPED", f"plugin missing at {plugin} — clone repo there")


def install_windsurf(home: Path, dry: bool):
    note("windsurf", "SKIPPED",
         "/etc/windsurf/hooks.json is root-owned — add manually:\n"
         f'  {{ "PreToolUse": [{{ "command": "python3 {HOOK}" }}] }}')


def install_gateway(home: Path, dry: bool):
    r = subprocess.run(["systemctl", "is-active", "blindfold-gateway"],
                       capture_output=True, text=True, timeout=10)
    if r.stdout.strip() == "active":
        note("gateway", "OK", "systemd service active — point base URL at http://127.0.0.1:8488/v1")
    else:
        note("gateway", "SKIPPED", "service not active — see deploy/blindfold-gateway.service")


def install_openwebui(home: Path, dry: bool):
    note("openwebui", "SKIPPED",
         "manual import: Admin Panel -> Functions -> paste adapters/openwebui/filter.py")


INSTALLERS = {
    "claude-code": install_claude_code,
    "cursor": install_cursor,
    "qcli": install_qcli,
    "codex": install_codex,
    "hermes": install_hermes,
    "windsurf": install_windsurf,
    "gateway": install_gateway,
    "openwebui": install_openwebui,
}


def probe(home: Path) -> int:
    """Verify each registered hook actually blocks a secret / passes clean."""
    values = os.environ.get("BLINDFOLD_VALUES", "")
    if not values:
        vf = home / ".blindfold" / "values.env"
        values = vf.read_text() if vf.exists() else ""
    secrets = [v for v in values.split("\n") if v]
    ok = True
    for name, hook in (("generic", HOOK), ("qcli", QCLI_HOOK)):
        if not hook.exists():
            note(f"probe:{name}", "SKIPPED", "hook file missing")
            continue
        for payload, expect, label in (
            # generic hook scans every string (any schema); qcli hook reads toolInput
            ({"tool_name": "Write", "tool_input": {"content": secrets[0]},
              "toolName": "Write", "toolInput": {"input": secrets[0]}} if secrets else {},
             2, "blocks secret"),
            ({"tool_name": "Write", "tool_input": {"content": "clean text"},
              "toolName": "Write", "toolInput": {"input": "clean text"}}, 0, "passes clean"),
        ):
            r = subprocess.run([sys.executable, str(hook)],
                               input=json.dumps(payload), capture_output=True, text=True,
                               env={**os.environ, "BLINDFOLD_VALUES": "\n".join(secrets)},
                               timeout=15)
            status = "OK" if r.returncode == expect else "FAILED"
            if r.returncode != expect:
                ok = False
            note(f"probe:{name}", status, f"{label} (rc={r.returncode}, want {expect})")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--home", default=str(Path.home()))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    home = Path(args.home)

    if args.target == "probe":
        rc = probe(home)
        _print()
        return rc

    values = discover_values(home)
    write_values_file(home, values, args.dry_run)
    os.environ["BLINDFOLD_VALUES"] = "\n".join(values)

    targets = list(INSTALLERS) if args.target == "all" else [args.target]
    for t in targets:
        fn = INSTALLERS.get(t)
        if fn is None:
            note(t, "FAILED", f"unknown harness; known: {', '.join(sorted(INSTALLERS))}, all, probe, refresh-values")
            continue
        try:
            fn(home, args.dry_run)
        except Exception as e:
            note(t, "FAILED", f"{type(e).__name__}: {e}")
    _print()
    return 0 if all(s != "FAILED" for _, s, _ in RESULTS) else 1


def _print():
    for harness, status, detail in RESULTS:
        print(f"{status:10} {harness:12} {detail}")


if __name__ == "__main__":
    sys.exit(main())

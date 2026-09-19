#!/usr/bin/env python3
"""Cross-adapter probe-suite gate: one suite, same verdicts, every adapter.

This is the standardisasi pengecekan from the roadmap. An adapter ships only
if this is green against it. Run:

    python3 tests/probe_suite/run.py --adapter hermes
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def import_adapter(name: str):
    if name == "hermes":
        sys.path.insert(0, str(ROOT / "adapters" / "hermes"))
        from blindfold.adapters.hermes import scan, register_secrets, DEFAULT_MAX_SECRETS
        return scan, register_secrets, DEFAULT_MAX_SECRETS
    raise SystemExit(f"unknown adapter: {name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default="hermes")
    ap.add_argument("--max-secrets", type=int, default=50)
    args = ap.parse_args()

    scan, register_secrets, DEFAULT_MAX_SECRETS = import_adapter(args.adapter)
    print(f"adapter: {args.adapter}")

    # The adapter must reach the real registry for this to mean anything.
    try:
        import agent.redact as redact  # noqa: F401
    except ImportError:
        raise SystemExit("probe-suite requires the real agent.redact on sys.path")

    print(f"[1] discovery finds .env + env secrets (register path)")
    probe = f"BLF_PROBE_{'k' * 16}"
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"blf-probe-{os.getpid()}"
    tmp.mkdir(0o700, exist_ok=True)
    (tmp / ".env").write_text(f"PROBE_API_KEY={probe}\n")
    os.environ["BLF_PROBE_TOKEN"] = probe
    res = scan(cwd=tmp, hermes_home=tmp)
    check("scan returned a count", isinstance(res, dict) and "registered" in res, str(res))
    check("scan registered >= 1", res["registered"] >= 1, json.dumps(res))

    print("[2] leak: registered values (raw + 4 transforms) all masked")
    from agent.redact import redact_sensitive_text
    probes = {"raw": probe, "base64": base64.b64encode(probe.encode()).decode(),
              "hex": probe.encode().hex(), "reversed": probe[::-1],
              "url": __import__("urllib.parse", fromlist=["quote"]).quote(probe, safe="")}
    leaks = [t for t, v in probes.items() if redact_sensitive_text(v) == v]
    check("0 of 5 probes leak", not leaks, f"leaked: {leaks}")

    print("[3] evict: batch under budget, none lost")
    redact.clear_vault_redaction_values()
    batch = {f"BLF_STRESS_{i:04d}": f"stress-secret-{i:04d}-{'x' * 16}" for i in range(args.max_secrets)}
    n = register_secrets(batch)
    check(f"registered {args.max_secrets}/{args.max_secrets}", n == args.max_secrets, f"got {n}")
    lost = []
    for i in range(args.max_secrets):
        v = batch[f"BLF_STRESS_{i:04d}"]
        if redact_sensitive_text(v) != v and redact_sensitive_text(v.encode().hex()) != v.encode().hex():
            continue
        lost.append(i)
    check("0 evicted", not lost, f"lost: {lost[:5]}{'…' if len(lost) > 5 else ''} ({len(lost)})")

    print("[4] hard boundary: vault values scrubbed regardless of the redact_secrets flag")
    # redact_sensitive_text calls redact_registered_vault_values() UNCONDITIONALLY
    # before the _REDACT_ENABLED gate (redact.py:681). Register a fresh value
    # (check [3] cleared the bucket), then disable the toggle and assert the
    # value is still masked. That is the hard-boundary contract.
    fresh = f"BLF_HARD_{'h' * 16}"
    import agent.redact as redact
    redact.register_vault_redaction_value(fresh)
    disabled = redact._REDACT_ENABLED
    redact._REDACT_ENABLED = False
    try:
        still = redact_sensitive_text(fresh) != fresh
    finally:
        redact._REDACT_ENABLED = disabled
    check("vault value masked with redaction disabled", still,
          redact_sensitive_text(fresh))

    print("[5] spoof: core importable from adapter context (fail-closed surface)")
    try:
        from core import TRANSFORMS  # noqa: F401
        spoof_ok = True
    except ImportError:
        spoof_ok = False
    check("core importable from adapter context", spoof_ok)

    os.environ.pop("BLF_PROBE_TOKEN", None)
    (tmp / ".env").unlink(missing_ok=True)
    tmp.rmdir()
    print("\n" + ("ALL GREEN" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

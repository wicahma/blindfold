"""Blindfold core — harness-agnostic secret discovery + transform registry.

DILARANG import apapun dari harness di sini. Bug di discovery = fix sekali,
bukan per-harness. Adapter hanya terjemahkan API harness ke kontrak ini.
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from urllib.parse import quote

__all__ = [
    "SENSITIVE_NAME",
    "NEVER_SECRET",
    "MIN_LEN",
    "TRANSFORMS",
    "VAULT_SLOT_MULTIPLIER",
    "is_sensitive",
    "discover_env",
    "discover_dotenv",
    "discover_all",
    "transforms_of",
]

# Secret-shaped env var names. Harness keyword scanners cover the keyword half;
# this catches names that carry a real secret but no keyword (verified leak class).
SENSITIVE_NAME = re.compile(
    r"^(.*_(TOKEN|SECRET|API_KEY|APIKEY|PASSWORD|PASSWD|PASS|KEY|CREDENTIAL)"
    r"|SUDO_PASSWORD|.*_SESSION_(KEY|TOKEN)|CONNECTION_STRING|.*_URL_WITH_CRED)$"
)
NEVER_SECRET = frozenset({
    "PATH", "HOME", "USER", "SHELL", "PWD", "LANG", "LC_ALL", "TERM", "HOSTNAME",
    "SSH_AUTH_SOCK", "DISPLAY", "EDITOR", "TMPDIR", "XDG_RUNTIME_DIR",
})
MIN_LEN = 8

# Encodings an agent can emit to exfiltrate a known value past a pattern scanner.
# Registering them makes the exact-substring scrub form-invariant.
TRANSFORMS = (
    ("base64", lambda v: base64.b64encode(v.encode()).decode()),
    ("hex", lambda v: v.encode().hex()),
    ("reversed", lambda v: v[::-1]),
    ("url", lambda v: quote(v, safe="")),
)
VAULT_SLOT_MULTIPLIER = 1 + len(TRANSFORMS)  # raw value + transforms


def is_sensitive(name: str, value: str) -> bool:
    """Name says it's a secret → register unconditionally.

    Deliberately NO entropy/shape test on the value: judging it re-introduces
    the false-negative class (a weak password that "doesn't look secret") that
    this exists to close.
    """
    if name in NEVER_SECRET or name.endswith("_SESSION") or len(value) < MIN_LEN:
        return False
    return bool(SENSITIVE_NAME.match(name))


def transforms_of(value: str) -> list[str]:
    """Every registered encoding of a secret, in TRANSFORMS order."""
    return [fn(value) for _, fn in TRANSFORMS]


def discover_env() -> dict[str, str]:
    out = {}
    for name, value in os.environ.items():
        if is_sensitive(name, value):
            out[name] = value
    return out


def discover_dotenv(roots: list[Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob(".env*")):
            if path.suffix in (".example", ".sample", ".template"):
                continue
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip().removeprefix("export ").strip()
                val = val.strip().strip("\"'").strip()
                if is_sensitive(key, val):
                    out.setdefault(f"{path.name}:{key}", val)
    return out


def discover_all(roots: list[Path]) -> dict[str, str]:
    """Merge process env + dotenv. Env wins on bare-name collisions."""
    return {**discover_dotenv(roots), **discover_env()}

"""Blindfold — register project secrets + transforms into Hermes' hard redaction boundary.

Hermes already scans tool output for credential patterns (agent/redact.py) and blocks
.env reads (agent/file_safety.py). Two real gaps remain (verified, see
~/notes/blindfold/04-verification-hermes-native.md):

  1. Secrets with a non-keyword var name (RANDOM_VAR=<real password>) never match.
  2. Any secret's TRANSFORM (base64/hex/reversed/url-encoded) never matches — the
     classic exfil channel; register_vault_redaction_value() only stores raw bytes.

Fix for both: register the exact value AND each transform into the vault registry.
The registry is an exact-substring scrub on every model-facing surface and is a hard
boundary (runs even when security.redact_secrets is false). Transforms are cheap:
k=4 string ops per value, O(n*k) per scrub.
"""
from __future__ import annotations

import base64
import logging
import os
import re
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger(__name__)

SENSITIVE_NAME = re.compile(
    r"^(.*_(TOKEN|SECRET|API_KEY|APIKEY|PASSWORD|PASSWD|PASS|KEY|CREDENTIAL)"
    r"|SUDO_PASSWORD|.*_SESSION_(KEY|TOKEN)|CONNECTION_STRING|.*_URL_WITH_CRED)$"
)
NEVER_SECRET = frozenset({
    "PATH", "HOME", "USER", "SHELL", "PWD", "LANG", "LC_ALL", "TERM", "HOSTNAME",
    "SSH_AUTH_SOCK", "DISPLAY", "EDITOR", "TMPDIR", "XDG_RUNTIME_DIR",
})
MIN_LEN = 8

_TRANSFORMS = (
    ("base64", lambda v: base64.b64encode(v.encode()).decode()),
    ("hex", lambda v: v.encode().hex()),
    ("reversed", lambda v: v[::-1]),
    ("url", lambda v: quote(v, safe="")),
)

_VAULT_SLOT_MULTIPLIER = 1 + len(_TRANSFORMS)  # value + transforms
DEFAULT_MAX_SECRETS = 500

def _is_sensitive(name: str, value: str) -> bool:
    if name in NEVER_SECRET or name.endswith("_SESSION") or len(value) < MIN_LEN:
        return False
    return bool(SENSITIVE_NAME.match(name))

def discover_env() -> dict[str, str]:
    out = {}
    for name, value in os.environ.items():
        if _is_sensitive(name, value):
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
                if _is_sensitive(key, val):
                    out.setdefault(f"{path.name}:{key}", val)
    return out

def register_secrets(secrets: dict[str, str]) -> int:
    """Register each value and its transforms into the hard vault-redaction boundary."""
    try:
        import agent.redact as redact
        from agent.redact import register_vault_redaction_value
    except ImportError:
        logger.warning("blindfold: agent.redact unavailable; plugin disabled")
        return 0
    needed = DEFAULT_MAX_SECRETS * _VAULT_SLOT_MULTIPLIER
    if redact._VAULT_REDACTION_MAX_PER_PROFILE < needed:
        redact._VAULT_REDACTION_MAX_PER_PROFILE = needed
    n = 0
    for name, value in secrets.items():
        if not value or len(value) < MIN_LEN:
            continue
        register_vault_redaction_value(value)
        n += 1
        for tname, fn in _TRANSFORMS:
            try:
                register_vault_redaction_value(fn(value))
            except Exception:
                logger.debug("blindfold: transform %s failed for %s", tname, name)
    return n

def scan(**_kwargs) -> dict:
    """Discover and register. Called on session start and on demand."""
    roots = [Path.cwd()]
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        roots.append(Path(hermes_home))
    secrets = {**discover_env(), **discover_dotenv(roots)}
    n = register_secrets(secrets)
    logger.info("blindfold: registered %d secret(s) (+ transforms) from %d source(s)", n, len(secrets))
    return {"registered": n, "sources": len(secrets)}

def register(ctx):
    """Hermes plugin entry point.

    on_session_start has no runtime fire-site (only in tests); on_session_reset /
    on_session_finalize are fired by cli_session_mixin._notify_session_boundary on
    every /new and /reset — the real session-boundary moments."""
    ctx.register_hook("on_session_reset", lambda **kw: scan())
    ctx.register_hook("on_session_finalize", lambda **kw: scan())
    ctx.register_hook("pre_tool_call", _pre_tool_call)

_FILE_TOOLS = frozenset({"read_file", "read_files", "cat", "terminal", "execute_code",
                         "bash", "shell", "web_extract"})

def _pre_tool_call(*, tool: str = "", command: str = "", args_raw: str = "",
                   **_kwargs) -> None:
    """Re-scan for secrets created mid-session, right before a file-reading tool runs."""
    if not tool or tool.lower() not in _FILE_TOOLS:
        return
    try:
        scan()
    except Exception:
        logger.debug("blindfold: pre_tool_call rescan failed", exc_info=True)

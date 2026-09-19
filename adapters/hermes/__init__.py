"""Blindfold Hermes adapter — thin. No security logic here.

TIPIS: hanya terjemahkan API Hermes ke kontrak core. Semua logika discovery +
transform ada di core/. Sebuah bug di discovery = fix sekali di core.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from ...core import (  # re-export the contract, do not reimplement
    SENSITIVE_NAME, NEVER_SECRET, MIN_LEN, TRANSFORMS, VAULT_SLOT_MULTIPLIER,
    is_sensitive, discover_env, discover_dotenv, discover_all, transforms_of,
)

__all__ = [
    "SENSITIVE_NAME", "NEVER_SECRET", "MIN_LEN", "TRANSFORMS", "VAULT_SLOT_MULTIPLIER",
    "is_sensitive", "discover_env", "discover_dotenv", "discover_all", "transforms_of",
    "scan_roots", "register_secrets", "scan", "register", "_pre_tool_call",
    "DEFAULT_MAX_SECRETS",
]

logger = logging.getLogger(__name__)

DEFAULT_MAX_SECRETS = 500

# ponytail: pre_tool_call is observer-only in v1, but we don't need to block —
# we only need to learn a new secret BEFORE its value reaches the model, and
# registration is effective immediately for the redaction pass on the result.
# Only tool calls that read a file can introduce a .env secret into context.
_FILE_TOOLS = frozenset({"read_file", "read_files", "cat", "terminal",
                         "execute_code", "bash", "shell", "web_extract"})


def scan_roots(cwd: Path, hermes_home: str | Path | None) -> list[Path]:
    roots = [Path(cwd)]
    if hermes_home:
        roots.append(Path(hermes_home))
    return roots


def register_secrets(secrets: dict[str, str]) -> int:
    """Register each value and its transforms into the hard vault-redaction boundary."""
    try:
        import agent.redact as redact
        from agent.redact import register_vault_redaction_value
    except ImportError:
        logger.warning("blindfold: agent.redact unavailable; plugin disabled")
        return 0
    # Bucket is bounded per profile; each secret costs 1 + n_transforms slots,
    # so the default cap silently LRU-evicts ~12 secrets in. Raise it first.
    # ponytail: module-global monkeypatch, not a core edit — the constant is
    # read at runtime in register_vault_redaction_value, so it survives without
    # touching agent/redact.py. Upgrade path if Hermes exposes a config key:
    # read it here and drop the patch.
    needed = DEFAULT_MAX_SECRETS * VAULT_SLOT_MULTIPLIER
    if redact._VAULT_REDACTION_MAX_PER_PROFILE < needed:
        redact._VAULT_REDACTION_MAX_PER_PROFILE = needed
    n = 0
    for name, value in secrets.items():
        if not value or len(value) < MIN_LEN:
            continue
        register_vault_redaction_value(value)
        n += 1
        for tname, fn in TRANSFORMS:
            try:
                register_vault_redaction_value(fn(value))
            except Exception:
                logger.debug("blindfold: transform %s failed for %s", tname, name)
    return n


def scan(cwd: Path | None = None, hermes_home: str | Path | None = None, **_kw) -> dict:
    """Discover and register. Called on session boundary and on demand."""
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    if hermes_home is None:
        hermes_home = os.environ.get("HERMES_HOME")
    secrets = discover_all(scan_roots(cwd, hermes_home))
    n = register_secrets(secrets)
    logger.info("blindfold: registered %d secret(s) (+ transforms) from %d source(s)", n, len(secrets))
    return {"registered": n, "sources": len(secrets)}


def register(ctx):
    """Hermes plugin entry point.

    on_session_start has no runtime fire-site (only in tests); on_session_reset /
    on_session_finalize are fired by cli_session_mixin._notify_session_boundary on
    every /new and /reset — the real session-boundary moments.
    """
    ctx.register_hook("on_session_reset", lambda **kw: scan())
    ctx.register_hook("on_session_finalize", lambda **kw: scan())
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    # Coverage for oneshot (-z) / paths that never fire a session-boundary hook:
    # the first terminal tool run lazily discovers + masks in the same pass.
    ctx.register_hook("transform_terminal_output", _transform_terminal_output)


def _pre_tool_call(*, tool: str = "", tool_name: str = "", command: str = "",
                   args_raw: str = "", **_kwargs) -> None:
    """Re-scan for secrets created mid-session, right before a file-reading tool runs.

    Hermes passes tool_name= (plugins.py _get_pre_tool_call_directive_details);
    tool= kept for older callers/tests.
    """
    name = (tool or tool_name or "").lower()
    if not name or name not in _FILE_TOOLS:
        return
    try:
        scan()
    except Exception:
        logger.debug("blindfold: pre_tool_call rescan failed", exc_info=True)


def _transform_terminal_output(*, output: str = "", command: str = "", **_kw):
    """Lazily scan then mask terminal output.

    Oneshot mode (`hermes -z`) never fires on_session_reset, so the vault can be
    empty when the first tool runs. This hook scans once (idempotent — vault
    registration dedupes) and masks before the builtin pattern pass. Returning
    None keeps the other transform hooks in play; only a mask returns a string.
    """
    if not output:
        return None
    try:
        scan()
        from agent.redact import redact_sensitive_text
        masked = redact_sensitive_text(output)
        return masked if masked != output else None
    except Exception:
        logger.debug("blindfold: terminal transform failed", exc_info=True)
        return None

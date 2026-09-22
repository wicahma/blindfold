"""Blindfold Hermes adapter — thin wiring, no security logic here.

core/ owns discovery + transforms. vault.py owns agent.redact access.
scanner.py owns tool-result secret detection. hooks.py owns hook callbacks.
cli.py owns the `hermes blindfold` subcommand.
This file only re-exports the contract and wires hooks in register().
"""
from __future__ import annotations

import logging

from ...core import (  # noqa: F401
    SENSITIVE_NAME, NEVER_SECRET, MIN_LEN, TRANSFORMS, VAULT_SLOT_MULTIPLIER,
    is_sensitive, discover_env, discover_dotenv, discover_all, transforms_of,
)
from . import cli as _cli
from . import persist, watch
from .hooks import (  # noqa: F401
    scan_roots, scan, _pre_tool_call, _transform_tool_result,
    _transform_terminal_output, _transform_llm_output,
)
from . import vault
from .vault import DEFAULT_MAX_SECRETS, register_secrets  # noqa: F401

logger = logging.getLogger(__name__)

__all__ = [
    "SENSITIVE_NAME", "NEVER_SECRET", "MIN_LEN", "TRANSFORMS", "VAULT_SLOT_MULTIPLIER",
    "is_sensitive", "discover_env", "discover_dotenv", "discover_all", "transforms_of",
    "scan_roots", "register_secrets", "scan", "register", "_pre_tool_call",
    "DEFAULT_MAX_SECRETS",
]


def register(ctx):
    """Hermes plugin entry point. Session boundaries rescan; tool hooks cover
    the paths that never fire a session boundary."""
    enabled = ctx.get_config("enabled", True)
    if enabled is False:
        logger.info("blindfold: disabled via plugins.entries.blindfold.settings.enabled")
        return
    max_secrets = ctx.get_config("max_secrets")
    if isinstance(max_secrets, int) and max_secrets > 0:
        vault.DEFAULT_MAX_SECRETS = max_secrets
    ctx.register_hook("on_session_reset", lambda **kw: scan())
    ctx.register_hook("on_session_finalize", lambda **kw: scan())
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("transform_tool_result", _transform_tool_result)
    ctx.register_hook("transform_terminal_output", _transform_terminal_output)
    ctx.register_hook("transform_llm_output", _transform_llm_output)
    _cli.register_cli(ctx)
    restored = persist.restore()
    if restored:
        logger.info("blindfold: restored %d learned value(s) from cache", restored)
    try:
        import os
        from pathlib import Path
        roots = [Path.cwd()]
        home = os.environ.get("HERMES_HOME")
        if home:
            roots.append(Path(home))
        watch.start(roots, scan)
    except Exception:
        logger.debug("blindfold: watcher start failed", exc_info=True)

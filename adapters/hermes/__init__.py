"""Blindfold Hermes adapter — thin wiring, no security logic here.

core/ owns discovery + transforms. vault.py owns agent.redact access.
scanner.py owns tool-result secret detection. hooks.py owns hook callbacks.
This file only re-exports the contract and wires hooks in register().
"""
from __future__ import annotations

from ...core import (  # noqa: F401
    SENSITIVE_NAME, NEVER_SECRET, MIN_LEN, TRANSFORMS, VAULT_SLOT_MULTIPLIER,
    is_sensitive, discover_env, discover_dotenv, discover_all, transforms_of,
)
from .hooks import (  # noqa: F401
    scan_roots, scan, _pre_tool_call, _transform_tool_result,
    _transform_terminal_output, _transform_llm_output,
)
from .vault import DEFAULT_MAX_SECRETS, register_secrets  # noqa: F401

__all__ = [
    "SENSITIVE_NAME", "NEVER_SECRET", "MIN_LEN", "TRANSFORMS", "VAULT_SLOT_MULTIPLIER",
    "is_sensitive", "discover_env", "discover_dotenv", "discover_all", "transforms_of",
    "scan_roots", "register_secrets", "scan", "register", "_pre_tool_call",
    "DEFAULT_MAX_SECRETS",
]


def register(ctx):
    """Hermes plugin entry point. Session boundaries rescan; tool hooks cover
    the paths that never fire a session boundary."""
    ctx.register_hook("on_session_reset", lambda **kw: scan())
    ctx.register_hook("on_session_finalize", lambda **kw: scan())
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("transform_tool_result", _transform_tool_result)
    ctx.register_hook("transform_terminal_output", _transform_terminal_output)
    ctx.register_hook("transform_llm_output", _transform_llm_output)

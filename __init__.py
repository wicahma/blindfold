"""Blindfold — secret masking for AI agents.

Repo root IS the Hermes plugin package: install as ~/.hermes/plugins/blindfold.
Security logic lives in core/ (harness-agnostic); Hermes wiring in
adapters/hermes/. This file re-exports the adapter entry points and adds
nothing of its own.
"""
from .adapters.hermes import (  # noqa: F401
    register, scan, register_secrets, scan_roots, _pre_tool_call,
    SENSITIVE_NAME, NEVER_SECRET, MIN_LEN, TRANSFORMS, VAULT_SLOT_MULTIPLIER,
    is_sensitive, discover_env, discover_dotenv, discover_all, transforms_of,
    DEFAULT_MAX_SECRETS,
)

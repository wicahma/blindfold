"""Vault registration wrapper — one seam for all agent.redact access.

Importing agent.redact at module scope breaks outside Hermes; everything here
imports lazily and fails soft.
"""
from __future__ import annotations

import logging

from ...core import MIN_LEN, TRANSFORMS, VAULT_SLOT_MULTIPLIER

logger = logging.getLogger(__name__)

DEFAULT_MAX_SECRETS = 500


def _redact_module():
    try:
        import agent.redact as redact
        return redact
    except ImportError:
        logger.warning("blindfold: agent.redact unavailable; plugin disabled")
        return None


def raise_bucket_cap() -> None:
    redact = _redact_module()
    if redact is None:
        return
    needed = DEFAULT_MAX_SECRETS * VAULT_SLOT_MULTIPLIER
    if redact._VAULT_REDACTION_MAX_PER_PROFILE < needed:
        redact._VAULT_REDACTION_MAX_PER_PROFILE = needed


def register_one(value: str) -> bool:
    redact = _redact_module()
    if redact is None or not value or len(value) < MIN_LEN:
        return False
    redact.register_vault_redaction_value(value)
    for name, fn in TRANSFORMS:
        try:
            redact.register_vault_redaction_value(fn(value))
        except Exception:
            logger.debug("blindfold: transform %s failed", name)
    return True


def register_secrets(secrets: dict[str, str]) -> int:
    raise_bucket_cap()
    return sum(1 for v in secrets.values() if register_one(v))


def redact_text(text: str) -> str:
    redact = _redact_module()
    if redact is None:
        return text
    return redact.redact_sensitive_text(text)


def vault_size() -> int | None:
    redact = _redact_module()
    if redact is None:
        return None
    try:
        return len(redact._VAULT_REDACTION_VALUES.get(redact._vault_scope(), {}))
    except Exception:
        return None


def learn_value(value: str) -> bool:
    """Register an already-known-secret value from any surface."""
    return register_one(value)


__all__ = [
    "DEFAULT_MAX_SECRETS", "raise_bucket_cap", "register_one", "register_secrets",
    "redact_text", "vault_size", "learn_value",
]

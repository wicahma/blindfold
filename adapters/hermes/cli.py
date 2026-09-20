"""Blindfold CLI — hermes blindfold status.

Shows vault size, discovered sources, registered count, and hook wiring.
Registered via ctx.register_cli_command in the plugin register().
"""
from __future__ import annotations

from . import hooks, vault


def _status_lines() -> list[str]:
    res = hooks.scan()
    n_vals = vault.vault_size()
    lines = [
        f"registered : {res['registered']} secret(s)",
        f"sources    : {res['sources']} (.env entries + env vars)",
        f"vault slots: {n_vals if n_vals is not None else 'unavailable (agent.redact missing)'}",
        f"max secrets: {vault.DEFAULT_MAX_SECRETS} (bucket cap "
        f"{vault.DEFAULT_MAX_SECRETS * 5})",
    ]
    return lines


def _cmd_status(args) -> None:
    print("blindfold status")
    print("-" * 40)
    for line in _status_lines():
        print(line)


def _setup(sub) -> None:
    sub.add_parser("status", help="vault size, sources, scan result").set_defaults(
        func=_cmd_status)


def register_cli(ctx) -> None:
    ctx.register_cli_command(
        "blindfold", "Blindfold secret-masking plugin commands",
        setup_fn=_setup, description="status / scan / config inspection")

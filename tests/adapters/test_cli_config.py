#!/usr/bin/env python3
"""Config gating + CLI registration contract tests (no Hermes runtime needed)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import blindfold.adapters.hermes as adapter  # noqa: E402
from blindfold.adapters.hermes import vault  # noqa: E402

FAIL = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        FAIL.append(name)


class FakeCtx:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.hooks = []
        self.cli = []

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, cb):
        self.hooks.append(name)

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.cli.append(name)


print("[1] default register: 6 hooks + 1 CLI command")
ctx = FakeCtx()
adapter.register(ctx)
check("6 hooks", len(ctx.hooks) == 6)
check("all expected hooks", set(ctx.hooks) == {
    "on_session_reset", "on_session_finalize", "pre_tool_call",
    "transform_tool_result", "transform_terminal_output", "transform_llm_output"})
check("cli command registered", ctx.cli == ["blindfold"])

print("[2] enabled=false disables all wiring")
ctx2 = FakeCtx({"enabled": False})
adapter.register(ctx2)
check("no hooks", ctx2.hooks == [])
check("no cli", ctx2.cli == [])

print("[3] max_secrets overrides the vault budget")
old = vault.DEFAULT_MAX_SECRETS
ctx3 = FakeCtx({"max_secrets": 50})
adapter.register(ctx3)
check("budget overridden", vault.DEFAULT_MAX_SECRETS == 50)
vault.DEFAULT_MAX_SECRETS = old

print("[4] non-int max_secrets ignored")
ctx4 = FakeCtx({"max_secrets": "lots"})
adapter.register(ctx4)
check("budget unchanged", vault.DEFAULT_MAX_SECRETS == old)

print("\nALL GREEN" if not FAIL else f"\nFAILED: {FAIL}")
sys.exit(1 if FAIL else 0)

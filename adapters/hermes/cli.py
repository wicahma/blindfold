"""Blindfold CLI — hermes blindfold status / sweep.

status: vault size, discovered sources, registered count.
sweep:  retroactively scan session transcripts in ~/.hermes/state.db for
        secrets that leaked before they were registered, report hits and
        learn them into the vault + persistent cache.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import hooks, persist, scanner, vault


def _status_lines() -> list[str]:
    res = hooks.scan()
    n_vals = vault.vault_size()
    return [
        f"registered : {res['registered']} secret(s)",
        f"sources    : {res['sources']} (.env entries + env vars)",
        f"vault slots: {n_vals if n_vals is not None else 'unavailable (agent.redact missing)'}",
        f"max secrets: {vault.DEFAULT_MAX_SECRETS} (bucket cap "
        f"{vault.DEFAULT_MAX_SECRETS * 5})",
        f"cache      : {persist.CACHE_PATH} "
        f"({'exists' if persist.CACHE_PATH.is_file() else 'empty'})",
    ]


def _cmd_status(args) -> None:
    print("blindfold status")
    print("-" * 40)
    for line in _status_lines():
        print(line)


def _db_path() -> Path:
    import os
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    return home / "state.db"


def _cmd_sweep(args) -> None:
    db_path = _db_path()
    if not db_path.is_file():
        print(f"sweep: no session db at {db_path}")
        return
    session_filter = getattr(args, "session_id", None)
    query = "SELECT session_id, id, content FROM messages WHERE content IS NOT NULL"
    params: tuple = ()
    if session_filter:
        query += " AND session_id = ?"
        params = (session_filter,)
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = db.execute(query, params)
    hits = 0
    learned = 0
    sessions_hit: set[str] = set()
    for sid, mid, content in rows:
        if not isinstance(content, str):
            continue
        found = scanner.find_secrets(content)
        if not found:
            continue
        hits += 1
        sessions_hit.add(sid)
        for value in found:
            learned += persist.learn(value)
    db.close()
    print("blindfold sweep")
    print("-" * 40)
    print(f"db           : {db_path}")
    print(f"messages hit : {hits} across {len(sessions_hit)} session(s)")
    print(f"learned      : {learned} new value(s) into vault + cache")
    if hits:
        print("note         : past transcripts stay on disk unmodified; "
              "learned values are masked in all future turns")


def _setup(parser) -> None:
    subs = parser.add_subparsers(dest="blindfold_command")
    subs.add_parser("status", help="vault size, sources, scan result").set_defaults(
        func=_cmd_status)
    sp = subs.add_parser("sweep", help="retroactively scan session transcripts")
    sp.add_argument("session_id", nargs="?", default=None,
                    help="restrict to one session id")
    sp.set_defaults(func=_cmd_sweep)


def register_cli(ctx) -> None:
    ctx.register_cli_command(
        "blindfold", "Blindfold secret-masking plugin commands",
        setup_fn=_setup, description="status / sweep / config inspection")

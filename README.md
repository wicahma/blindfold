# Blindfold

Keep secrets out of your LLM's context window — without breaking the agent.

Works on **any agent harness**: Hermes, Claude Code, Codex CLI, Gemini/Antigravity,
Cline, Cursor, Windsurf, Amazon Q CLI, Open WebUI, ChatGPT Desktop — via one
universal gateway, thin per-harness adapters, and one standardized probe suite.

**Problem:** agent harnesses scan tool output for credential *patterns* (vendor
prefixes like `sk-`, `xoxb-`, `eyJh`). Two leaks survive that approach:

1. **Non-patterned secrets** — a `SUDO_PASSWORD=correcthorse` in `.env` has no
   vendor prefix and never matches. The harness reads it and passes it to the model.
2. **Transformed secrets** — once a raw value is known, `base64`, `hex`,
   `reversed`, or URL-encoded variants of it sail through the same scanner.

**Fix:** register the *actual values* (and their transforms) into the harness's
exact-substring scrub boundary. No patterns, no guessing — if the bytes match,
they get masked before the model sees them.

## What it does

Blindfold is a **Hermes Agent plugin** (~150 lines, stdlib only) that:

- scans `.env` files and environment variables for secret-shaped names/values
- registers each value **+ 4 transforms** (base64/hex/reversed/url-encoded) into
  `agent.redact`'s hard redaction boundary
- raises the registry's per-profile bucket threshold so a real secret count
  doesn't silently LRU-evict older entries
- rescans on session boundary and before any file-reading tool — so secrets
  created mid-session are also covered

The result: `redact_sensitive_text()` masks the value everywhere it appears,
on every model-facing surface, in any form.

```python
# before
>>> redact_sensitive_text("SUDO_PASSWORD=correcthorse")
"SUDO_PASSWORD=[REDACTED]"      # wait — leaks: no vendor prefix

# after Blindfold registers the value
>>> redact_sensitive_text(base64.b64encode(b"correcthorse").decode())
"[REDACTED]"                     # the transform is caught too
```

## Architecture

```
core/                    harness-agnostic. No harness imports. Bug = one fix.
  discovery (.env*/env) + transforms (base64/hex/reversed/url) + name-gate
adapters/                THIN. Translate a harness API into the core contract.
  hermes/                Hermes plugin (hooks wired at session + tool boundary)
  gateway/               UNIVERSAL DEFAULT — OpenAI-compatible reverse proxy
                         (LiteLLM CustomLogger + zero-dep stdlib server).
                         6/7 CLI harnesses + Claude Desktop covered by one
                         base-URL override.
  hooks/generic_block.py block-only shim for Claude Code, Codex CLI, Cline,
                         Cursor, Windsurf, Q CLI (JSON stdin → exit 2)
  qcli/hook.py           Amazon Q CLI (the one harness without base-URL)
  openwebui/filter.py    Filter Function: inlet/outlet, toggle locked False
  mcp/server.py          COMPANION ONLY (scan + probe tools; cannot intercept)
tests/
  core/  adapters/       unit + adapter-contract tests
  probe_suite/run.py     THE gate: same 5-check suite, every adapter
  e2e/stress/mid/sweep   original Hermes regression suites
```

**Enforcement matrix (verified Sept 2026, see docs/ARCHITECTURE.md):**
masking = gateway (any harness with a base-URL override). Blocking =
`generic_block.py`. Discovery/probe from chat = MCP companion. An adapter
ships only when the full probe-suite is green against it.

## Install

**Hermes** (drop-in plugin):

```bash
git clone https://github.com/wicahma/blindfold ~/.hermes/plugins/blindfold
hermes config set plugins.enabled '["bots-dashboard","superpowers","blindfold"]'
hermes gateway restart     # from a shell OUTSIDE the running gateway
```

**Any OpenAI-compatible harness** (gateway — one env var / config field):

```bash
python3 -m blindfold.adapters.gateway.server --port 8080 --upstream https://api.openai.com
# then point the harness's base URL at http://127.0.0.1:8080/v1
# LiteLLM users: add the BlindfoldHandler INSTANCE to litellm_settings.callbacks
```

**Block-only hook** (Claude Code / Codex / Cline / Cursor / Windsurf / Q CLI):
register `adapters/hooks/generic_block.py` in the harness's hook config
(paths in the module docstring), with `BLINDFOLD_VALUES` populated once from
`core.discover_all()` + `core.transforms_of()`.

**Open WebUI**: import `adapters/openwebui/filter.py` as a Function (Admin
Panel → Functions). Toggle is locked off — users cannot disable it.

**ChatGPT Desktop** (no other surface): MCP companion — run
`adapters/mcp/server.py` over stdio; gives `blindfold_scan` + `blindfold_probe`.

No dependencies beyond the Python stdlib (LiteLLM optional for the proxy-hook
variant).

## How it works

The insight is that **registration beats pattern-matching** for secrets you
already know. Hermes' `agent/redact.py` already has a fast exact-substring scrub
pass (`register_vault_redaction_value`), but its vault registry is only populated
by the browser-autofill path. Blindfold points it at the secrets that actually
matter: your project's `.env`.

```
.env ─┐
      ├─► scan() ─► for each secret:
osenv ─┘              register_vault_redaction_value(raw)
                      register_vault_redaction_value(base64(v))
                      register_vault_redaction_value(hex(v))
                      register_vault_redaction_value(reversed(v))
                      register_vault_redaction_value(url_encoded(v))
                                    │
                                    ▼
                    agent.redact exact-substring scrub
                                    │
                                    ▼
                          model never sees the bytes
```

Two details that bit during development:

- **Threshold.** The registry bucket is bounded per profile. Registering 5
  entries per secret against a threshold of 64 means ~12 secrets before LRU
  eviction silently drops coverage. Budget `max_secrets * (1 + n_transforms)`.
  See `tests/stress_threshold.py`.
- **Hook fire-sites.** `on_session_start` has no runtime fire-site in Hermes
  (tests only) — registering there is a silent no-op. Use `on_session_reset` /
  `on_session_finalize`, which fire on every `/new` and `/reset`.
  `tests/e2e_hermes.py` asserts the hooks are actually wired.

## Scope

Blindfold covers secrets that exist as `.env` entries or environment variables at
scan time. It does **not** intercept:

- secrets first emitted by a non-file tool (e.g. an API returning a fresh token
  in a JSON body) until the next file-reading tool runs — closing that needs
  `transform_tool_result`, which sits on the token path
- secrets never scanned at all (a key typed into a prompt by the user)

For unknown-secret discovery, combine with a scanner like `gitleaks` or
`trufflehog`. They're complementary: scanners *find*, Blindfold *enforces*.

## Files

| Path | Role |
|---|---|
| `core/__init__.py` | Harness-agnostic contract: discovery, transforms, name-gate |
| `adapters/hermes/` | Hermes plugin (scan, register, session + tool hooks) |
| `adapters/gateway/` | Universal proxy: `mask.py`, `litellm_hook.py`, `build.py`, `server.py` |
| `adapters/hooks/generic_block.py` | Block-only shim, 6 harnesses |
| `adapters/qcli/hook.py` | Amazon Q CLI block hook |
| `adapters/openwebui/filter.py` | Open WebUI Filter Function |
| `adapters/mcp/server.py` | MCP companion (scan + probe) |
| `tests/probe_suite/run.py` | Cross-adapter gate: leak/evict/hard-boundary/spoof |
| `tests/e2e_hermes.py` | End-to-end against real Hermes discovery + real `.env` |
| `tests/stress_threshold.py` | Bucket-threshold regression (300 secrets, 0 evicted) |
| `tests/test_mid_session.py` | Mid-session secret pickup via `pre_tool_call` |
| `blindfold-core.py` | Standalone slot-machine prototype (slot refs, type-preserving redact, exec bridge) |

## Documentation

- **[docs/FEATURES.md](docs/FEATURES.md)** — every feature, how it works, and the
  test that proves it. Start here.
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — where each piece lives, which
  Hermes primitive it touches, and the failure modes.
- Research notes live outside this repo, in the author's SilverBullet vault at
  `notes/blindfold/` — the 16-tool survey and the gap verification this
  plugin was built from.

## Research background

Built from a survey of 16 secret-protection tools (SlotGuard, EnvForge,
pi-secret-firewall, cc-redact, nopeek, MCP guardrails). The full analysis —
strengths/weaknesses per tool, which gaps apply to Hermes and which don't, and
the verification evidence — see `notes/blindfold/` in the author's vault.

## License

MIT

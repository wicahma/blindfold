# Blindfold

<p align="center">
  <img src="assets/banner.png" alt="Blindfold — secrets stay secret. even from your agent." width="720">
</p>

<p align="center">
  <a href="https://github.com/wicahma/blindfold/stargazers"><img src="https://img.shields.io/github/stars/wicahma/blindfold?style=flat-square" alt="Stars"></a>
  <a href="https://github.com/wicahma/blindfold/actions"><img src="https://img.shields.io/github/actions/workflow/status/wicahma/blindfold/ci.yml?branch=main&style=flat-square" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/wicahma/blindfold?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/python-stdlib%20only-ff3b3b?style=flat-square" alt="stdlib only">
</p>

<p align="center">
  Keep secrets out of your LLM's context window — <em>without breaking the agent</em>.
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> · <a href="#how-it-works">How it works</a> · <a href="#adapters">Adapters</a> · <a href="docs/FEATURES.md">Docs</a>
</p>

---

## Why

Agent harnesses scan tool output for credential *patterns* — vendor prefixes
like `sk-`, `xoxb-`, `eyJh`. Two leaks survive:

1. **Non-patterned secrets** — `SUDO_PASSWORD=*** has no
   vendor prefix and never matches. The harness reads it and passes it to the
   model verbatim.
2. **Transformed secrets** — once a raw value is known, `base64`, `hex`,
   `reversed`, or URL-encoded variants sail through the same scanner.

Blindfold takes the opposite approach: **register the actual values** (and their
transforms) into the harness's exact-substring scrub boundary. No patterns, no
guessing — if the bytes match, they get masked before the model sees them.

```
$ echo $DB_PASSWORD
«redacted-vault-secret»

$ echo $DB_PASSWORD | base64
«redacted-vault-secret»
```

## Quickstart

**Hermes Agent** — drop-in plugin:

```bash
git clone https://github.com/wicahma/blindfold ~/.hermes/plugins/blindfold
hermes config set plugins.enabled '["blindfold"]'
hermes gateway restart
```

Every assistant response now carries a live status footer:

```
---
🛡 blindfold: active — 20 secret(s) registered from 20 source(s), 42 vault slots
```

**One-command installer** (all supported harnesses):

```bash
python3 blindfold_install.py all && python3 blindfold_install.py probe
```

Injects hooks into Claude Code, Cursor, Codex CLI, Amazon Q CLI; writes
`~/.blindfold/values.env` (chmod 600); idempotent, atomic, backs up first.

## How it works

Registration beats pattern-matching for secrets you already know.

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
                    exact-substring scrub on every model-facing surface
                                    │
                                    ▼
                          model never sees the bytes
```

Two details that bit during development:

- **Bucket threshold.** The registry is bounded per profile. 5 entries per
  secret against a cap of 64 means ~12 secrets before LRU eviction silently
  drops coverage. Blindfold raises it to `max_secrets * (1 + n_transforms)`
  (see `tests/stress_threshold.py`).
- **Hook fire-sites.** `on_session_start` has no runtime fire-site in Hermes —
  registering there is a silent no-op. Use `on_session_reset` /
  `on_session_finalize`, plus a lazy scan on the first file-reading tool so
  one-shot mode (`hermes -z`) is covered too.

## Adapters

Enforcement matrix (verified Sept 2026, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)):
masking = universal gateway; blocking = `generic_block.py`; discovery/probe from
chat = MCP companion. An adapter ships only when the full probe suite is green.

| Harness | Surface | Mode |
|---|---|---|
| Hermes Agent | plugin (hooks) | mask + block |
| Claude Code, Codex CLI, Cline, Cursor, Windsurf | `adapters/hooks/generic_block.py` | block |
| Any OpenAI-compatible harness | `adapters/gateway/server.py` (reverse proxy, LiteLLM optional) | mask |
| Amazon Q CLI | `adapters/qcli/hook.py` | block |
| Open WebUI | `adapters/openwebui/filter.py` (Function, toggle locked) | mask |
| ChatGPT Desktop (no hook surface) | `adapters/mcp/server.py` | scan + probe |

No dependencies beyond the Python stdlib (LiteLLM optional for the proxy-hook
variant).

## Scope

Covers secrets that exist as `.env` entries or environment variables at scan
time. It does **not** intercept:

- secrets first emitted by a non-file tool (an API returning a fresh token in a
  JSON body) until the next file-reading tool runs — closing that needs
  `transform_tool_result`, which sits on the token path
- secrets never scanned at all (a key typed into a prompt by the user)

For unknown-secret discovery, combine with `gitleaks` or `trufflehog` —
scanners *find*, Blindfold *enforces*.

## Files

| Path | Role |
|---|---|
| `core/` | Harness-agnostic contract: discovery, transforms, name-gate |
| `adapters/hermes/` | Hermes plugin (scan, register, session + tool + output hooks) |
| `adapters/gateway/` | Universal proxy: `mask.py`, `litellm_hook.py`, `build.py`, `server.py` |
| `adapters/hooks/generic_block.py` | Block-only shim, 6 harnesses |
| `blindfold_install.py` | One-command cross-harness installer + probe |
| `tests/probe_suite/` | Cross-adapter gate: leak/evict/hard-boundary/spoof |
| `tests/e2e_hermes.py` | End-to-end against real Hermes discovery + real `.env` |
| `tests/stress_threshold.py` | Bucket-threshold regression (300 secrets, 0 evicted) |
| `tests/adapters/test_hook_filecontent.py` | Read/Bash file-content block regressions |

## Documentation

- **[docs/FEATURES.md](docs/FEATURES.md)** — every feature, how it works, and the
  test that proves it. Start here.
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — where each piece lives, which
  Hermes primitive it touches, and the failure modes.

## Research background

Built from a survey of 16 secret-protection tools (SlotGuard, EnvForge,
pi-secret-firewall, cc-redact, nopeek, MCP guardrails).

## License

MIT

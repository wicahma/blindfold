# Blindfold

Keep secrets out of your LLM's context window — without breaking the agent.

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

## Install

```bash
git clone https://github.com/wicahma/blindfold ~/.hermes/plugins/blindfold
hermes config set plugins.enabled '["bots-dashboard","superpowers","blindfold"]'
hermes gateway restart     # from a shell OUTSIDE the running gateway
```

That's it. The next session boundary (`/new` or `/reset`) triggers the first scan.
`pre_tool_call` fires on every file-reading tool, so secrets created mid-session
are picked up without a restart.

No dependencies beyond the Python stdlib and Hermes Agent itself.

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

| File | Role |
|---|---|
| `blindfold.py` | Plugin: scan, register, hooks |
| `blindfold-core.py` | Standalone slot-machine prototype (slot refs, type-preserving redact, exec bridge) |
| `plugin.yaml` | Hermes plugin manifest |
| `tests/e2e_hermes.py` | End-to-end against real Hermes discovery + real `.env` |
| `tests/stress_threshold.py` | Bucket-threshold regression (300 secrets, 0 evicted) |
| `tests/test_mid_session.py` | Mid-session secret pickup via `pre_tool_call` |

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

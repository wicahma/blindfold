"""LiteLLM callback shim — the module users point litellm_settings.callbacks at.

LiteLLM resolves the config string `custom_callbacks.proxy_handler_instance` to
a module attribute. Pointing at an INSTANCE is the documented working form;
a bare class is a silent no-op (hook registered, never errors, never masks).

Secrets come from BLINDFOLD_VALUES (newline-separated, raw + transforms) so the
same registry the hook shims use drives the gateway path too.
"""
import os
import sys
from pathlib import Path

_pkg_candidates = [
    Path(os.environ.get("BLINDFOLD_PACKAGE_ROOT", "")) if os.environ.get("BLINDFOLD_PACKAGE_ROOT") else None,
    Path.home() / ".hermes" / "plugins",
    Path(__file__).resolve().parent.parent.parent,
]
for _p in _pkg_candidates:
    if _p and _p.is_dir() and (_p / "blindfold").is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from blindfold.adapters.gateway.litellm_hook import BlindfoldHandler  # noqa: E402

_values = [v for v in os.environ.get("BLINDFOLD_VALUES", "").split("\n") if v]

# litellm_settings.callbacks: ["blindfold_callback.proxy_handler_instance"]
proxy_handler_instance = BlindfoldHandler(secrets=_values)
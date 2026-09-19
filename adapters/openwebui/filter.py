"""Blindfold Open WebUI Filter Function — native in-process masking.

Can be loaded directly into Open WebUI via Admin Panel -> Functions.
Provides inlet (pre-LLM) and outlet (post-LLM) secret scrubbing.

Security rule: toggle MUST be False to prevent chat users from disabling
the redaction pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core import discover_all, transforms_of
from ..gateway.mask import mask_messages, mask_response


class Filter:
    def __init__(self):
        # Open WebUI standard toggle attribute — False means ALWAYS ACTIVE / CANNOT BE DISABLED by users
        self.toggle = False
        self.values: List[str] = []
        self._load_secrets()

    def _load_secrets(self, roots: Optional[List[Path]] = None):
        discovered = discover_all(roots or [Path.cwd()])
        vals = []
        for v in discovered.values():
            if not v:
                continue
            vals.append(v)
            vals.extend(transforms_of(v))
        self.values = vals

    def set_secrets(self, secrets: List[str]):
        """Override secrets list explicitly (used in tests/runtime configuration)."""
        self.values = [s for s in secrets if s]

    def inlet(self, body: Dict[str, Any], __user__: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Called before the request is forwarded to the LLM backend."""
        return mask_messages(body, self.values)

    def outlet(self, body: Dict[str, Any], __user__: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Called before the response is returned to the client UI."""
        return mask_response(body, self.values)

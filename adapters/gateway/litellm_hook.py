"""Blindfold LiteLLM proxy hook — the universal enforcement point.

Subclass CustomLogger and override the call hooks. Proxy-only (not SDK).
Config in litellm_settings:

    callbacks:
      custom_callbacks.proxy_handler_instance

Point at the INSTANCE, not the class — a class is a documented silent no-op
(the hook runs but never errors). This is the same bug class as Hermes'
on_session_start, and it silently disables a security boundary.

Request is masked before it leaves; response is masked before it returns.
Because 6/7 CLI harnesses plus Claude Desktop expose a base-URL override,
this one adapter covers them all with no per-harness hook code.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .mask import mask_messages, mask_response

logger = logging.getLogger(__name__)


class BlindfoldHandler:
    """LiteLLM CustomLogger-compatible handler.

    liteellm.integrations.custom_logger.CustomLogger is the real base class;
    it is imported lazily in register_for_litellm() so this module stays
    importable (and testable) where litellm is not installed.
    """

    def __init__(self, secrets: Optional[list[str]] = None):
        # secrets: raw values + their transforms, from core.discover_all()
        self.values = [v for v in (secrets or []) if v]

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict,
        call_type: str,
    ) -> dict:
        """Mask the request body before it is sent upstream."""
        try:
            return mask_messages(data, self.values)
        except Exception:
            logger.exception("blindfold: pre-call mask failed; blocking request")
            raise  # fail closed: never let a masking error send a raw secret

    async def async_post_call_success_hook(
        self,
        data: dict,
        user_api_key_dict: Any,
        response: Any,
    ) -> None:
        """Mask the response body in place before it is returned."""
        if isinstance(response, dict):
            masked = mask_response(response, self.values)
            response.clear()
            response.update(masked)

    async def async_post_call_streaming_hook(
        self,
        user_api_key_dict: Any,
        response: str,
    ) -> str:
        """Mask a streaming chunk before it is returned."""
        return mask_response(response, self.values) if isinstance(response, dict) else response

    def register_for_litellm(self) -> list:
        """Return the handler instance list for litellm_settings.callbacks."""
        return [self]

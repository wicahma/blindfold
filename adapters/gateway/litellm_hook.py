"""Blindfold LiteLLM proxy hook — the universal enforcement point.

Config in litellm_settings:

    litellm_settings:
      callbacks: ["blindfold_callback.proxy_handler_instance"]

Point at the INSTANCE, not the class — LiteLLM validates callbacks with
isinstance(CustomLogger) and a bare class is rejected (older versions
silently no-op'd instead). Request is masked before it leaves; response is
masked before it returns. Because 6/7 CLI harnesses plus Claude Desktop
expose a base-URL override, this one adapter covers them all with no
per-harness hook code.

When litellm is installed, BlindfoldHandler dynamically subclasses the real
CustomLogger (the proxy's isinstance check demands it). Without litellm the
class still imports and the direct-call contract tests still run.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .mask import mask_messages, mask_response

logger = logging.getLogger(__name__)


def _base_class() -> type:
    """Real CustomLogger when litellm is present, plain object otherwise."""
    try:
        from litellm.integrations.custom_logger import CustomLogger
        return CustomLogger
    except ImportError:
        return object


_BlindfoldBase = _base_class()


class BlindfoldHandler(_BlindfoldBase):
    """LiteLLM callback handler: masks request + response bodies.

    Subclasses the real CustomLogger when litellm is installed so the proxy's
    isinstance validation accepts it; plain object otherwise (contract tests).
    """

    def __init__(self, secrets: Optional[list[str]] = None):
        # secrets: raw values + their transforms, from core.discover_all()
        self.values = [v for v in (secrets or []) if v]
        try:
            super().__init__()
        except TypeError:
            pass  # plain-object base

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
        user_api_key_dict: Any,
        data: dict,
        response: Any,
    ) -> Any:
        """Mask the response body before it is returned to the client.

        LiteLLM calls this with keyword args and replaces `response` with the
        returned value. The router hands back a ModelResponse object (not a
        dict), so mask the message strings on the object; dicts go through the
        recursive scrub.
        """
        try:
            if isinstance(response, dict):
                return mask_response(response, self.values)
            # ModelResponse object: mask content strings in place
            for ch in (getattr(response, "choices", None) or []):
                msg = getattr(ch, "message", None)
                content = getattr(msg, "content", None)
                if isinstance(content, str) and content:
                    masked = mask_messages(content, self.values)
                    if masked != content:
                        msg.content = masked
                delta = getattr(ch, "delta", None)
                dcontent = getattr(delta, "content", None)
                if isinstance(dcontent, str) and dcontent:
                    masked = mask_messages(dcontent, self.values)
                    if masked != dcontent:
                        delta.content = masked
            return response
        except Exception:
            logger.exception("blindfold: post-call mask failed; blocking response")
            raise  # fail closed

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

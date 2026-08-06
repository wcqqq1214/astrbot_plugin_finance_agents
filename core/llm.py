"""Adapter over AstrBot's LLM provider abstraction."""

from __future__ import annotations

from typing import Any


class LLMError(Exception):
    """Raised when the configured provider cannot serve a request."""


class LLMAdapter:
    """Thin wrapper exposing a single ``chat()`` call over a provider."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    async def chat(self, system_prompt: str, user_content: str) -> str:
        """Send one chat turn and return the plain-text completion."""

        try:
            resp = await self._provider.text_chat(
                prompt=user_content,
                context=[],
                system_prompt=system_prompt,
            )
        except Exception as exc:
            raise LLMError(f"LLM request failed: {type(exc).__name__}: {exc}") from exc
        text = getattr(resp, "completion_text", "") or ""
        if not text:
            raise LLMError("LLM returned an empty response.")
        return text


def create_llm(context: Any, umo: str) -> LLMAdapter:
    """Build an adapter over the provider currently in use for ``umo``."""

    provider = context.get_using_provider(umo=umo)
    if provider is None:
        raise LLMError("No LLM provider is configured in AstrBot.")
    return LLMAdapter(provider)

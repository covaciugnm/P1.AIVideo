"""Scriptwriter provider registry.

Resolves ``SCRIPTWRITER_BACKEND`` to a concrete ``ScriptProvider``.
Providers are lazy-imported INSIDE ``resolve()`` so that an environment
missing (for example) a future ``openai`` dependency can still resolve
the ``template`` provider with no error.

Adding a new backend in a future phase only requires editing this file
plus the ``providers/<name>/provider.py`` module — no DAG or backend
change is needed. Operators opt into a new backend by flipping
``SCRIPTWRITER_BACKEND`` in their ``.env``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from common.exceptions import UnsupportedBackendError

if TYPE_CHECKING:
    from agents.scriptwriter.core.provider import ScriptProvider


_KNOWN_BACKENDS: tuple[str, ...] = (
    "template",
    "mock",  # alias for template
    "ollama",
    "vllm",
    "openai_compatible",
    "openai",
    "anthropic",
    "local_http",
)


def known_backends() -> list[str]:
    """Stable list of backend names this registry can resolve."""
    return list(_KNOWN_BACKENDS)


def resolve(name: str) -> "ScriptProvider":
    """Return a fresh provider instance for the given backend name."""
    n = (name or "").lower().strip()
    if n in ("template", "mock"):
        from agents.scriptwriter.providers.template.provider import TemplateProvider

        return TemplateProvider()
    if n == "ollama":
        from agents.scriptwriter.providers.ollama.provider import OllamaProvider

        return OllamaProvider()
    if n == "vllm":
        from agents.scriptwriter.providers.vllm.provider import VLLMProvider

        return VLLMProvider()
    if n == "openai_compatible":
        from agents.scriptwriter.providers.openai_compatible.provider import (
            OpenAICompatibleProvider,
        )

        return OpenAICompatibleProvider()
    if n == "openai":
        from agents.scriptwriter.providers.openai.provider import OpenAIProvider

        return OpenAIProvider()
    if n == "anthropic":
        from agents.scriptwriter.providers.anthropic.provider import AnthropicProvider

        return AnthropicProvider()
    if n == "local_http":
        from agents.scriptwriter.providers.local_http.provider import LocalHTTPProvider

        return LocalHTTPProvider()
    raise UnsupportedBackendError(
        f"unknown SCRIPTWRITER_BACKEND={name!r}; known: {_KNOWN_BACKENDS}"
    )

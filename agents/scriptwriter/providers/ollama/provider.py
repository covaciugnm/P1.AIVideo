"""Ollama scriptwriter provider — Phase 8G real generation.

Real HTTP call to a local Ollama daemon. Uses stdlib ``urllib.request``
only (no new dependencies). Network calls are gated globally by
``SCRIPTWRITER_ENABLE_NETWORK_CALLS=true`` at the API layer; this
module respects that and never opens a socket at import time.

Behavior summary:

- ``healthcheck()`` pings ``{OLLAMA_BASE_URL}/api/tags`` with a short
  timeout. It returns:
    - ``not_implemented`` when ``SCRIPTWRITER_ENABLE_NETWORK_CALLS`` is
      off (preserves Phase 3G default — the registry stays disabled by
      default);
    - ``not_configured`` when the daemon is unreachable;
    - ``ok`` when the daemon is reachable AND the preferred model (or
      the fallback) is listed.
- ``generate()`` POSTs to ``{OLLAMA_BASE_URL}/api/chat`` with a JSON-
  formatted prompt. It tries the preferred model first, falls back to
  ``OLLAMA_FALLBACK_MODEL`` on a 404 (model-not-found). Result parsing
  is forgiving: if the model returns valid JSON we use it directly,
  otherwise we segment the raw text into hook/body/cta.
- Errors are raised as ``ProviderNotImplementedError`` with a categorised
  message prefix so the existing ``/api/v1/script/generate`` 503 mapper
  routes them correctly:
    - "unreachable: ..."        → ``script_provider_unreachable``
    - "model_missing: ..."      → ``script_provider_unreachable`` (UI shows model gap)
    - "malformed_response: ..." → ``script_generation_failed``

No new pip deps. No new compose service. The operator must already
have an Ollama daemon reachable (host, sidecar, or
``compose.dev.yml::model-llm`` under ``--profile llm``).
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, ClassVar

from common.enums import ProviderHealthStatus
from common.exceptions import ProviderNotImplementedError
from common.schemas import ProviderHealth

from agents.scriptwriter.core.provider import (
    ScriptProvider,
    ScriptRequest,
    ScriptResult,
)


# Wall-clock cap on the Ollama call. Local models on CPU take 5-30s for
# a short reel script; we set a generous bound. The healthcheck uses a
# much smaller timeout so the API surface stays snappy.
_GENERATE_TIMEOUT_SECONDS = 90
_HEALTHCHECK_TIMEOUT_SECONDS = 3
_PROMPT_VERSION = "ollama-v1"


def _network_enabled() -> bool:
    return os.environ.get("SCRIPTWRITER_ENABLE_NETWORK_CALLS", "false").lower() == "true"


class OllamaProvider(ScriptProvider):
    provider_name: ClassVar[str] = "ollama"

    def __init__(self) -> None:
        model = os.environ.get("OLLAMA_MODEL", "qwen3.6")
        super().__init__(model_name=model)
        self._base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self._fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen3:8b")

    def required_config(self) -> list[str]:
        return ["OLLAMA_BASE_URL", "OLLAMA_MODEL"]

    # ----- Health -----

    def healthcheck(self) -> ProviderHealth:
        # Network calls disabled → stay deliberately ``not_implemented``
        # so the catalog renders the gate-off state Phase 3G defined.
        if not _network_enabled():
            return ProviderHealth(
                backend=self.provider_name,
                status=ProviderHealthStatus.not_implemented,
                errors=[
                    "ollama: SCRIPTWRITER_ENABLE_NETWORK_CALLS is false. "
                    "Set it to true to allow real generation."
                ],
                extra=self._extra_meta(),
            )

        try:
            tags = self._tags()
        except _OllamaUnreachable as exc:
            return ProviderHealth(
                backend=self.provider_name,
                status=ProviderHealthStatus.not_configured,
                errors=[f"ollama daemon unreachable at {self._base_url}: {exc}"],
                extra=self._extra_meta(),
            )

        if not _model_in_tags(self.model_name, tags):
            if not _model_in_tags(self._fallback_model, tags):
                return ProviderHealth(
                    backend=self.provider_name,
                    status=ProviderHealthStatus.missing_assets,
                    missing_assets=[self.model_name, self._fallback_model],
                    errors=[
                        f"neither preferred ({self.model_name}) nor fallback "
                        f"({self._fallback_model}) model is pulled in this Ollama "
                        f"daemon. Run `ollama pull {self.model_name}` "
                        "(or the fallback) manually — no auto-pull from this app."
                    ],
                    extra=self._extra_meta(),
                )
            # Fallback present, preferred missing — still reportable.
            return ProviderHealth(
                backend=self.provider_name,
                status=ProviderHealthStatus.ok,
                models_root=self._base_url,
                extra={
                    **self._extra_meta(),
                    "preferred_model_present": False,
                    "fallback_model_present": True,
                    "available_models": sorted(set(tags))[:25],
                },
            )

        return ProviderHealth(
            backend=self.provider_name,
            status=ProviderHealthStatus.ok,
            models_root=self._base_url,
            extra={
                **self._extra_meta(),
                "preferred_model_present": True,
                "fallback_model_present": _model_in_tags(
                    self._fallback_model, tags
                ),
                "available_models": sorted(set(tags))[:25],
            },
        )

    # ----- Generation -----

    async def generate(self, req: ScriptRequest) -> ScriptResult:
        if not _network_enabled():
            raise ProviderNotImplementedError(
                "ollama: SCRIPTWRITER_ENABLE_NETWORK_CALLS is false. "
                "Set it to true to allow real generation."
            )

        # Try preferred model first, fall back to OLLAMA_FALLBACK_MODEL
        # on a 404 / model-missing signal. Other errors propagate to the
        # API mapper untouched.
        tried_models: list[str] = []
        last_error: Exception | None = None
        for candidate in self._candidate_models():
            tried_models.append(candidate)
            try:
                raw = self._chat(model=candidate, prompt=_build_prompt(req))
                hook, body, cta, full_script, est_dur = _parse_or_segment(
                    raw, req
                )
                return ScriptResult(
                    hook=hook,
                    body=body,
                    cta=cta,
                    full_script=full_script,
                    estimated_duration_seconds=float(est_dur),
                    language=req.language,
                    provider=self.provider_name,
                    model=candidate,
                    prompt_version=_PROMPT_VERSION,
                    metadata={
                        "tried_models": list(tried_models),
                        "base_url": self._base_url,
                        "raw_response_length": len(raw),
                        "json_parsed": isinstance(_safe_json(raw), dict),
                    },
                )
            except _OllamaModelMissing as exc:
                last_error = exc
                # Try next candidate.
                continue
            except _OllamaUnreachable as exc:
                raise ProviderNotImplementedError(
                    f"unreachable: ollama daemon at {self._base_url} did not "
                    f"respond: {exc}"
                ) from exc
            except _OllamaMalformed as exc:
                raise ProviderNotImplementedError(
                    f"malformed_response: ollama returned an unexpected payload: {exc}"
                ) from exc

        # Exhausted all candidates without success.
        raise ProviderNotImplementedError(
            f"model_missing: none of {tried_models} are available in the "
            f"Ollama daemon at {self._base_url}. Last error: {last_error}"
        )

    # ----- Internals -----

    def _candidate_models(self) -> list[str]:
        out = [self.model_name]
        if self._fallback_model and self._fallback_model != self.model_name:
            out.append(self._fallback_model)
        return out

    def _extra_meta(self) -> dict[str, Any]:
        return {
            "base_url": self._base_url,
            "preferred_model": self.model_name,
            "fallback_model": self._fallback_model,
            "calls_external_apis": False,
        }

    def _tags(self) -> list[str]:
        url = self._base_url.rstrip("/") + "/api/tags"
        try:
            with urllib.request.urlopen(
                url, timeout=_HEALTHCHECK_TIMEOUT_SECONDS
            ) as resp:
                body = resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            raise _OllamaUnreachable(str(exc)) from exc
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise _OllamaUnreachable(f"non-JSON /api/tags: {exc}") from exc
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, list):
            return []
        return [str(m.get("name") or m.get("model") or "") for m in models if isinstance(m, dict)]

    def _chat(self, *, model: str, prompt: str) -> str:
        """POST /api/chat — non-streaming. Returns the model's reply text."""
        url = self._base_url.rstrip("/") + "/api/chat"
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": _SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            "options": {
                # Bounded response so a runaway model can't fill memory.
                "num_predict": 800,
                "temperature": 0.7,
            },
            "format": "json",
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_GENERATE_TIMEOUT_SECONDS) as resp:
                body_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            # 404 → model not available in this Ollama daemon.
            if exc.code == 404:
                raise _OllamaModelMissing(
                    f"ollama returned 404 for model {model!r}; pull it manually with "
                    f"`ollama pull {model}` if you have shell access to the daemon."
                ) from exc
            # 500 with body sometimes wraps a model-not-found too.
            try:
                err_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                err_body = ""
            if "model" in err_body.lower() and "not found" in err_body.lower():
                raise _OllamaModelMissing(err_body) from exc
            raise _OllamaUnreachable(f"HTTP {exc.code}: {err_body[:300]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise _OllamaUnreachable(str(exc)) from exc

        try:
            response = json.loads(body_bytes)
        except json.JSONDecodeError as exc:
            raise _OllamaMalformed(f"non-JSON response envelope: {exc}") from exc

        # Ollama /api/chat non-streaming envelope: {"message": {"content": "..."}, "done": true}
        if not isinstance(response, dict):
            raise _OllamaMalformed("response is not a JSON object")
        msg = response.get("message")
        if not isinstance(msg, dict):
            raise _OllamaMalformed("response.message missing")
        content = msg.get("content")
        if not isinstance(content, str):
            raise _OllamaMalformed("response.message.content missing")
        return content


# ---------------------------------------------------------------------------
# Internal error sentinels
# ---------------------------------------------------------------------------


class _OllamaUnreachable(Exception):
    """Daemon down / network error / non-JSON /api/tags."""


class _OllamaModelMissing(Exception):
    """Daemon up but the requested model is not pulled."""


class _OllamaMalformed(Exception):
    """Daemon returned something we can't parse."""


# ---------------------------------------------------------------------------
# Prompt builder + response parser
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = (
    "You are a short-form video scriptwriter for a synthetic reel "
    "generator. Always respond with a single JSON object containing "
    "keys: hook (string, <=80 chars), body (string, <=600 chars), cta "
    "(string, <=80 chars), full_script (string), "
    "estimated_duration_seconds (number), language (ISO 639-1). The "
    "tone must remain factual, brand-safe, and free of celebrity "
    "comparisons. Do not include any text outside the JSON object."
)


def _build_prompt(req: ScriptRequest) -> str:
    parts: list[str] = []
    parts.append(f"Brief: {req.brief.strip()}")
    parts.append(f"Target duration (seconds): {req.target_duration_seconds}")
    parts.append(f"Language: {req.language}")
    if req.tone:
        parts.append(f"Tone: {req.tone}")
    if req.platform:
        parts.append(f"Platform: {req.platform}")
    if req.audience:
        parts.append(f"Audience: {req.audience}")
    if req.script_text:
        parts.append(f"Operator-supplied draft (rewrite/improve):\n{req.script_text.strip()}")
    parts.append(
        "Reply with the JSON object only. Do not add explanations or "
        "Markdown fences."
    )
    return "\n".join(parts)


def _model_in_tags(name: str, tags: list[str]) -> bool:
    """Ollama tags carry a ``:tag`` suffix (``qwen3.6:latest``). A bare
    name should match the ``:latest`` flavour by convention."""
    if not name:
        return False
    if name in tags:
        return True
    if ":" not in name and f"{name}:latest" in tags:
        return True
    return False


def _safe_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try the first {...} fenced object — some models wrap their JSON
        # in ```json ... ``` fences despite the prompt.
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None


def _parse_or_segment(
    raw: str, req: ScriptRequest
) -> tuple[str, str, str, str, float]:
    """Forgiving parser: prefer JSON, fall back to deterministic
    sentence/paragraph segmentation. Always returns a structured tuple.
    """
    data = _safe_json(raw)
    target = float(req.target_duration_seconds)
    if isinstance(data, dict):
        hook = _coerce_str(data.get("hook"))
        body = _coerce_str(data.get("body"))
        cta = _coerce_str(data.get("cta"))
        full_script = _coerce_str(data.get("full_script"))
        if not full_script:
            full_script = "\n\n".join(part for part in (hook, body, cta) if part)
        est = data.get("estimated_duration_seconds")
        try:
            est_dur = float(est) if est is not None else target
        except (TypeError, ValueError):
            est_dur = target
        if hook or body or cta:
            # Even if some fields are empty, structured JSON wins —
            # downstream stages tolerate empty hook/cta.
            return hook, body, cta, full_script, est_dur

    # Fallback: deterministic segmentation of the raw text.
    text = raw.strip()
    if not text:
        return ("", "", "", "", target)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) >= 3:
        hook = paragraphs[0]
        cta = paragraphs[-1]
        body = "\n\n".join(paragraphs[1:-1])
    elif len(paragraphs) == 2:
        hook, body = paragraphs
        cta = ""
    else:
        # Single-paragraph: split by sentence boundaries.
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[\.\!\?])\s+", paragraphs[0] if paragraphs else text)
            if s.strip()
        ]
        if len(sentences) >= 3:
            hook = sentences[0]
            cta = sentences[-1]
            body = " ".join(sentences[1:-1])
        elif len(sentences) == 2:
            hook, body = sentences
            cta = ""
        else:
            hook = text
            body = ""
            cta = ""
    full_script = "\n\n".join(p for p in (hook, body, cta) if p)
    return hook, body, cta, full_script, target


def _coerce_str(v: Any) -> str:
    if isinstance(v, str):
        return v.strip()
    if v is None:
        return ""
    return str(v).strip()

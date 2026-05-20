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
# Phase 20 — the new cinematic JSON template is large, so generation
# can take longer on a 27B Q4 model; bump the cap accordingly.
_GENERATE_TIMEOUT_SECONDS = int(
    os.environ.get("OLLAMA_GENERATE_TIMEOUT_SECONDS", "300")
)
_HEALTHCHECK_TIMEOUT_SECONDS = 3
# Phase 20 — bump prompt version because both the system prompt and
# expected JSON shape changed. Downstream artifacts can still be
# replayed because the parser remains forgiving.
_PROMPT_VERSION = "ollama-unified-v4-topicanchored"


# Phase 20 — operator-tunable Ollama generation parameters. Defaults
# match the recipe the user pinned (Qwen-3.6 27B Q4 GGUF on a single
# GPU). Each one is env-overridable so we don't need a code change to
# A/B different settings.
def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _ollama_options() -> dict[str, Any]:
    """Phase 20 — generation params kept identical across calls so the
    same brief always produces the same script (modulo model
    stochasticity). Defaults pinned to the recipe the operator supplied
    for Qwen-3.6 27B Q4 GGUF.
    """
    # Default stop tokens — the Qwen chat template emits these markers
    # at the end of each turn. ``OLLAMA_STOP`` is a ``;;``-separated
    # override (cannot use ``|`` because the Qwen tokens themselves
    # contain ``|`` characters: ``<|im_end|>``). Operator can extend
    # without a code change. ``\n`` is a synonym separator for
    # operator convenience.
    raw_stop = os.environ.get(
        "OLLAMA_STOP", "<|im_end|>;;<|endoftext|>"
    ).strip()
    # Accept both ``;;`` and newline as separators.
    parts: list[str] = []
    for line in raw_stop.split("\n"):
        parts.extend(line.split(";;"))
    stop = [s for s in (token.strip() for token in parts) if s]
    return {
        "num_predict": _env_int("OLLAMA_NUM_PREDICT", 4096),
        "num_ctx": _env_int("OLLAMA_NUM_CTX", 8192),
        "temperature": _env_float("OLLAMA_TEMPERATURE", 0.7),
        "top_p": _env_float("OLLAMA_TOP_P", 0.9),
        "top_k": _env_int("OLLAMA_TOP_K", 20),
        "repeat_penalty": _env_float("OLLAMA_REPEAT_PENALTY", 1.05),
        "stop": stop,
    }


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
                raw = self._chat(
                    model=candidate,
                    prompt=_build_prompt(req),
                    mode=req.mode or "spoken_script",
                )
                hook, body, cta, full_script, est_dur, cinematic = _parse_or_segment(
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
                        # Phase 20 — keep the full cinematic JSON so
                        # downstream stages (editor/face/lipsync) can
                        # later consume scene_list, visual_style_guide,
                        # per-scene durations, etc. Empty dict when the
                        # model produced the legacy hook/body/cta shape.
                        "cinematic": cinematic,
                        # Phase 21 — also expose the parsed scenes list
                        # at the top of metadata so the API layer can
                        # lift it onto ``ScriptGenerateResponse.scenes``
                        # without re-parsing the JSON.
                        "scenes": (
                            cinematic.get("scenes")
                            if isinstance(cinematic, dict) else None
                        ),
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

    def _chat(self, *, model: str, prompt: str, mode: str = "spoken_script") -> str:
        """POST /api/chat — non-streaming. Returns the model's reply text.

        Phase 21 iter 2 — when ``mode="image_description"``, swap the
        system prompt for the visual-prompt writer template.
        """
        url = self._base_url.rstrip("/") + "/api/chat"
        if mode == "image_description":
            system_prompt = _IMAGE_DESCRIPTION_SYSTEM_PROMPT
        elif mode == "scene_plan":
            system_prompt = _SCENE_PLAN_SYSTEM_PROMPT
        else:
            system_prompt = _SYSTEM_PROMPT
        # Phase 21 iter 2 — keep_alive controls how long Ollama holds the
        # model in VRAM after the call. The 24GB RTX 5090 cannot hold
        # both qwen3.6:27b (~14GB) AND FLUX.1-schnell (~14GB)
        # simultaneously, so we set a short keep_alive when the FLUX
        # wrapper is also configured. Operator can override per env.
        flux_present = bool(os.environ.get("FLUX_LOCAL_BASE_URL", "").strip())
        keep_alive_default = "30s" if flux_present else os.environ.get(
            "OLLAMA_KEEP_ALIVE", "30m"
        )
        keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE_PER_CALL", keep_alive_default)
        payload = {
            "model": model,
            "stream": False,
            "keep_alive": keep_alive,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {"role": "user", "content": prompt},
            ],
            # Phase 20 — operator-tunable knobs (see _ollama_options()).
            "options": _ollama_options(),
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


# Phase 20 iter 3 — UNIFIED LLM contract.
#
# Empirical observation: neither qwen3.5:9b nor qwen3.6:27b-q4 actually
# follow the long cinematic JSON schema we pinned originally. qwen3.6
# naturally collapses to a clean 2-key shape `{"spoken_language",
# "script"}`; qwen3.5 simplifies even further (sometimes a list).
#
# To get IDENTICAL output across all backed LLMs we ask for the exact
# 2-key shape qwen3.6 produces. The parser still recognises the
# cinematic shape, the legacy hook/body/cta shape, and a wide range of
# fallback keys (script / scenariu / full_voiceover_text / story / …),
# so a future bigger model that happens to return the cinematic JSON
# still works without code changes. The downside (we lose per-scene
# camera/visual instructions in the JSON) is acceptable for the
# scenario PREVIEW step — production stages can run a second LLM pass
# with a stricter prompt when they need scene-level data.
_SYSTEM_PROMPT = (
    "You are a professional video script generator for short cinematic reels.\n\n"
    "Your task: transform the user's brief into a complete, "
    "production-ready SPOKEN SCRIPT for an AI video generation pipeline.\n\n"
    "ABSOLUTE TOPIC RULE — the most important rule:\n"
    "- The brief IS the subject of the video. Generate a script DIRECTLY "
    "ABOUT THE EXACT TOPIC described in the brief, whatever it is.\n"
    "- If the brief is a description, write a script about that description.\n"
    "- If the brief is a complaint, a meta-statement, a technical note, a "
    "question, an observation, a list, a single word, or anything else — "
    "treat it AS the subject of the video and build a script about it.\n"
    "- NEVER substitute a different, more 'video-friendly' topic. NEVER "
    "generate a script about Romania, NATO, EU, generic motivational "
    "themes, marketing, technology, lifestyle, or any topic the brief does "
    "NOT explicitly mention.\n"
    "- If the brief is too short or ambiguous, you MAY add cinematic "
    "framing, but the SUBJECT must stay identical to what the brief says.\n"
    "- The first sentence of the spoken script MUST clearly connect to "
    "the brief's actual subject — a reader who saw only the script must "
    "be able to guess the brief.\n\n"
    "You MUST understand Romanian input directly. Do NOT require the user to "
    "translate Romanian text into English.\n\n"
    "Preserve the user's core idea, main character, gender, language, tone, "
    "duration, style, target audience and constraints. Do NOT invent "
    "unrelated storylines.\n\n"
    "Avoid generic AI clichés, exaggerated marketing language, unrealistic "
    "promises, overdramatic scenes, fantasy elements, and unnecessary visual "
    "effects unless explicitly requested.\n\n"
    "Use short, natural sentences with clear punctuation for natural speech "
    "pauses. The script must be readable aloud by a text-to-speech engine.\n\n"
    "Length: pace at roughly 2.5 spoken words per second so the result fits "
    "the target duration the user gave.\n\n"
    "Structure: opening hook, substantive main body, brief closing "
    "call-to-action — written as one flowing readable text.\n\n"
    "REQUIRED OUTPUT — return EXACTLY this JSON object, no additional keys, "
    "no markdown fences, no prose outside the braces:\n\n"
    "{\n"
    '  "spoken_language": "<ISO 639-1 code from the user prompt, e.g. ro>",\n'
    '  "script": "<the complete spoken script as a single string in the '
    'spoken_language; NOT a list, NOT an object, NOT nested JSON>"\n'
    "}\n\n"
    "Hard rules (in priority order):\n"
    "1. The \"script\" content MUST be directly about the brief's topic. "
    "Off-topic = failure.\n"
    "2. The \"script\" field MUST be a single natural-language string.\n"
    "3. The \"script\" string MUST be written in the spoken_language. "
    "Romanian briefs MUST produce a Romanian script. English briefs "
    "MUST produce an English script. NEVER translate the brief.\n"
    "4. Do NOT wrap the script in arrays, do NOT split it into per-scene "
    "objects, do NOT add extra top-level keys."
)


# Phase 21 — scene-planner system prompt for ``mode="scene_plan"``.
# Produces a structured JSON list of segments that the operator can
# edit before triggering the scenes_only / news_presenter pipeline.
# Each segment has a kind ("presenter" or "broll"), spoken_text in the
# requested language, and (for broll) an English FLUX image prompt.
_SCENE_PLAN_SYSTEM_PROMPT = (
    "You are a professional video scene planner. Given a brief and a "
    "target total duration, you propose a sequence of 3–8 scenes that "
    "make up a coherent short video about the brief's exact topic.\n\n"
    "Each scene has:\n"
    "  - scene_number (1-based, sequential)\n"
    "  - kind: \"presenter\" OR \"broll\"\n"
    "    * presenter: a talking-head segment where a character speaks "
    "directly to the camera (the character portrait will be reused; "
    "the visual is the character themselves, NOT a generated scene)\n"
    "    * broll: a B-roll segment showing a still scene image with "
    "voiceover (NO character on screen; the visual comes from a FLUX "
    "text-to-image render)\n"
    "  - spoken_text: what is narrated DURING this scene, in the "
    "spoken_language requested\n"
    "  - visual_description: REQUIRED for broll, ignored for presenter. "
    "Single-line ENGLISH FLUX prompt — background, framing, lighting, "
    "render style. No people, no faces, no real brands, no text.\n"
    "  - duration_s: between 1.0 and 20.0 seconds; sum of all scenes "
    "MUST be within ±20% of the requested target duration\n\n"
    "ABSOLUTE RULES:\n"
    "1. spoken_text is in the brief's language; visual_description is "
    "ALWAYS in English (FLUX produces best results from English prompts).\n"
    "2. Stay strictly on the brief's TOPIC. Do not substitute generic "
    "subjects (NEVER Romania/NATO/EU unless the brief mentions them).\n"
    "3. Mix kinds based on operator intent passed via job_type_hint:\n"
    "   - if hint says \"scenes_only\": EVERY scene must be kind=broll\n"
    "   - if hint says \"news_presenter\": at least 1 presenter (open or "
    "close), and at least 1 broll. Interleave naturally.\n"
    "4. The first scene introduces the topic; the last scene closes "
    "with a brief call-to-action or summary.\n"
    "5. Use short, natural sentences for spoken_text (TTS-friendly).\n\n"
    "REQUIRED OUTPUT — return EXACTLY this JSON object, no other keys:\n\n"
    "{\n"
    '  "spoken_language": "<ISO 639-1 code, e.g. ro>",\n'
    '  "scenes": [\n'
    "    {\n"
    '      "scene_number": 1,\n'
    '      "kind": "presenter",\n'
    '      "spoken_text": "<sentence(s) in spoken_language>",\n'
    '      "visual_description": null,\n'
    '      "duration_s": 4.0\n'
    "    }\n"
    "  ]\n"
    "}"
)


# Phase 21 iter 2 — alternative system prompt for the
# ``mode="image_description"`` flow used by the talking-head form's
# "Generate image description" button. Produces a SHORT visual prompt
# (background + character outfit + pose + lighting) — not a spoken
# script. The output still ships through ``{"script": "<prompt>"}``
# so the existing parser → ``full_script`` plumbing keeps working;
# the frontend feeds that string straight into FLUX as the image prompt.
_IMAGE_DESCRIPTION_SYSTEM_PROMPT = (
    "You are an expert AI image-prompt writer for cinematic portrait "
    "photography.\n\n"
    "Your task: from the user's brief, write a SHORT visual prompt "
    "describing a single still photograph of the main character "
    "speaking. The image will be used as the static portrait that an "
    "AI lipsync model animates while a TTS narration plays.\n\n"
    "MUST include, in this order:\n"
    "  1. The setting / background (1 phrase — newsroom, sunlit kitchen, "
    "wooden study, outdoor park, …) that matches the brief's topic.\n"
    "  2. The character's outfit (1 phrase — clothes, colours, accessories) "
    "that fits the topic + the character's gender.\n"
    "  3. The pose + framing (medium shot, looking at camera, slight "
    "smile, …) — the character MUST face the camera since the mouth "
    "will be animated.\n"
    "  4. The lighting + mood (soft warm key light, golden hour, studio "
    "softbox, …).\n"
    "  5. Render style (photorealistic, cinematic, 35mm photography, "
    "sharp focus, …).\n\n"
    "RULES:\n"
    "- Output is a SINGLE line (200–400 characters).\n"
    "- English only — image models work best on English prompts even "
    "when the brief is in Romanian. Translate the topic intent to "
    "English visual language.\n"
    "- The framing MUST be front-facing medium close-up (face clearly "
    "visible, mouth unobstructed). Never side-profile, never full-body, "
    "never back view.\n"
    "- Do NOT include text, watermarks, logos, brand names, recognisable "
    "real people. Do NOT request multiple characters.\n"
    "- No camera moves, no scene breaks, no narrative — this is ONE "
    "still photo.\n\n"
    "REQUIRED OUTPUT — return EXACTLY this JSON object, no other keys, "
    "no markdown, no prose:\n\n"
    "{\n"
    '  "spoken_language": "<ISO 639-1 from user prompt, e.g. ro>",\n'
    '  "script": "<the single-line English visual prompt described above>"\n'
    "}"
)


def _build_prompt(req: ScriptRequest) -> str:
    # Phase 21 iter 2 — branch on output mode. The image_description
    # branch produces a SHORT English visual prompt for FLUX; the
    # default branch produces a spoken script (Phase 20 iter 4 prompt);
    # Phase 21 — scene_plan branch produces a list of segments.
    mode = (req.mode or "spoken_script").strip()
    if mode == "image_description":
        return _build_image_description_prompt(req)
    if mode == "scene_plan":
        return _build_scene_plan_prompt(req)

    # Phase 20 iter 4 — unified user-prompt context.
    # The brief is wrapped in clear delimiters and labelled VIDEO TOPIC
    # so the model does NOT treat it as background advice and substitute
    # a different subject (the iter-3 prompt occasionally produced
    # off-topic scripts about Romania/NATO/EU when the brief was a
    # short meta-statement).
    parts: list[str] = []
    lang = (req.language or "en").strip().lower()
    lang_label = _LANG_LABELS.get(lang, lang.upper())
    brief = req.brief.strip()

    # Topic anchor at the top — pinned BEFORE the language rule so the
    # model can't drift to a familiar Romanian subject before reading
    # the actual brief.
    parts.append(
        "VIDEO TOPIC (the subject of the script — generate the script "
        "DIRECTLY ABOUT THIS EXACT TEXT; do NOT substitute a different "
        "topic, do NOT generalise to a familiar subject):\n"
        "<<<BRIEF_START>>>\n"
        f"{brief}\n"
        "<<<BRIEF_END>>>"
    )
    parts.append(
        f"LANGUAGE: write the \"script\" string in {lang_label} (ISO "
        f"639-1 code: {lang}). Do NOT translate the brief to English. "
        f"The brief above is in {lang_label} — answer in the SAME "
        f"language."
    )
    parts.append(f"Target duration (seconds): {req.target_duration_seconds}")
    parts.append(f"spoken_language: {lang}")
    if req.tone:
        parts.append(f"Tone: {req.tone}")
    if req.platform:
        parts.append(f"Platform: {req.platform}")
    if req.audience:
        parts.append(f"Target audience: {req.audience}")
    if req.script_text:
        parts.append(
            "Operator-supplied draft (use as the starting point for the "
            "script; preserve intent and voice, still keep the topic "
            f"identical to the brief above):\n{req.script_text.strip()}"
        )
    parts.append(
        "Now produce the script. The first sentence MUST clearly "
        "connect to the brief's actual subject above — a reader who "
        "saw only the script must be able to guess the brief.\n\n"
        "Return EXACTLY:\n"
        "{\n"
        f'  "spoken_language": "{lang}",\n'
        '  "script": "<full spoken script about the brief above, as '
        'one readable string>"\n'
        "}\n"
        "No markdown fences. No prose outside the braces. The \"script\" "
        "value MUST be a single string (not a list, not an object), and "
        "MUST be directly about the brief topic between BRIEF_START and "
        "BRIEF_END."
    )
    return "\n\n".join(parts)


def _normalise_scenes_list(
    raw_scenes: list[Any], req: ScriptRequest
) -> list[dict[str, Any]]:
    """Phase 21 iter 2 — coerce a heterogeneous LLM scenes list into
    SceneSpec-shaped dicts. Models routinely emit ``duration_seconds``
    or ``visual_duration_seconds`` instead of ``duration_s``, omit
    ``scene_number``, and forget ``kind``. We:

    - rename common duration aliases to ``duration_s``
    - clamp duration_s to [1.0, 20.0]
    - auto-assign scene_number from list position when missing
    - infer kind from visual_description text (presenter cues: words
      like "presenter", "host", "speaker", "she speaks", "demonstrates",
      "looking at camera"; otherwise broll)
    - for scenes_only hint, force every scene to kind=broll
    """
    hint = ""
    if isinstance(req.metadata, dict):
        h = req.metadata.get("job_type_hint")
        if isinstance(h, str):
            hint = h.strip().lower()
    out: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_scenes, start=1):
        if not isinstance(raw, dict):
            continue
        # Duration alias mapping.
        duration: Any = (
            raw.get("duration_s")
            or raw.get("duration_seconds")
            or raw.get("visual_duration_seconds")
            or raw.get("duration")
            or raw.get("seconds")
        )
        try:
            duration_f = float(duration) if duration is not None else 5.0
        except (TypeError, ValueError):
            duration_f = 5.0
        duration_f = max(1.0, min(20.0, duration_f))

        scene_number = raw.get("scene_number") or raw.get("number") or idx
        try:
            scene_number = int(scene_number)
        except (TypeError, ValueError):
            scene_number = idx
        if scene_number < 1 or scene_number > 99:
            scene_number = idx

        visual = _coerce_str(raw.get("visual_description") or raw.get("visual"))
        spoken = _coerce_str(raw.get("spoken_text") or raw.get("text") or raw.get("narration"))

        kind = _coerce_str(raw.get("kind")).lower() or ""
        if kind not in ("presenter", "broll"):
            # Infer from visual_description cues.
            v = visual.lower()
            presenter_cues = (
                "presenter", "host ", "anchor", "the speaker", "she speaks",
                "he speaks", "looking at camera", "looks at camera",
                "speaks directly", "speaking to camera", "demonstrates",
                "raises her arms", "raises his arms", "smiles",
                "the woman speaks", "the man speaks",
            )
            if any(cue in v for cue in presenter_cues):
                kind = "presenter"
            else:
                kind = "broll"
        # scenes_only hint forces every scene to broll regardless.
        if hint == "scenes_only":
            kind = "broll"

        # Presenter scenes don't carry a visual prompt (they use the
        # character portrait); broll requires one.
        if kind == "presenter":
            visual = ""
        if kind == "broll" and not visual:
            visual = (
                "Cinematic still image illustrating: "
                + (spoken[:120] if spoken else "the topic")
            )

        out.append({
            "scene_number": scene_number,
            "kind": kind,
            "spoken_text": spoken,
            "visual_description": visual if kind == "broll" else None,
            "duration_s": round(duration_f, 1),
            "image_artifact_id": None,
            "audio_artifact_id": None,
            "clip_artifact_id": None,
        })
    # Renumber to be strictly sequential, preserving order.
    for i, s in enumerate(out, start=1):
        s["scene_number"] = i
    return out


def _build_scene_plan_prompt(req: ScriptRequest) -> str:
    """Phase 21 — user prompt for the scene-planner mode.

    The brief is wrapped in BRIEF_START/END delimiters; the target
    duration becomes the cap on the sum of scene durations. The
    ``job_type_hint`` (read from req.metadata["job_type_hint"], or
    derived from req.platform as a cheap fallback) tells the model
    whether to emit broll-only scenes or interleave presenter+broll.
    """
    brief = req.brief.strip()
    lang = (req.language or "en").strip().lower()
    lang_label = _LANG_LABELS.get(lang, lang.upper())
    # job_type_hint can ride on metadata OR platform.
    hint = ""
    if isinstance(req.metadata, dict):
        h = req.metadata.get("job_type_hint")
        if isinstance(h, str) and h.strip():
            hint = h.strip().lower()
    if not hint and req.platform:
        p = req.platform.strip().lower()
        if p in ("scenes_only", "news_presenter"):
            hint = p
    if hint not in ("scenes_only", "news_presenter"):
        hint = "news_presenter"  # safe default — emits hybrid plan
    # Character gender (for presenter scenes — purely informational).
    gender = ""
    if isinstance(req.metadata, dict):
        g = req.metadata.get("character_gender")
        if isinstance(g, str) and g.strip():
            gender = g.strip().lower()
    if not gender and req.tone:
        t = req.tone.strip().lower()
        if t in ("female", "male", "neutral"):
            gender = t
    parts: list[str] = []
    parts.append(
        "VIDEO TOPIC (the subject of every scene — stay strictly on it; "
        "do NOT substitute a familiar but different subject):\n"
        "<<<BRIEF_START>>>\n"
        f"{brief}\n"
        "<<<BRIEF_END>>>"
    )
    parts.append(
        f"LANGUAGE for spoken_text: {lang_label} (ISO {lang}). "
        "visual_description stays in English regardless."
    )
    parts.append(f"Target total duration: ~{req.target_duration_seconds}s (±20%)")
    parts.append(f"job_type_hint: {hint}")
    if gender and hint == "news_presenter":
        parts.append(f"Presenter character gender: {gender}")
    parts.append(
        "Return EXACTLY the JSON object specified in the system prompt. "
        "No markdown fences. No prose outside the braces. The first "
        "scene MUST connect to the topic above."
    )
    return "\n\n".join(parts)


def _build_image_description_prompt(req: ScriptRequest) -> str:
    """Phase 21 iter 2 — user prompt for image_description mode.

    Tells the model: the brief is a VIDEO TOPIC; produce a short
    English image prompt for the still portrait used by the lipsync
    stage. The character's gender is forwarded via ``req.tone`` (the
    frontend passes "female"/"male" there because the existing
    ScriptRequest schema has no dedicated gender field).
    """
    brief = req.brief.strip()
    # The operator can pass the character's gender either through
    # ``req.tone`` (cheap path used by the frontend) or via
    # ``req.metadata["character_gender"]``.
    gender = ""
    if isinstance(req.metadata, dict):
        g = req.metadata.get("character_gender") or req.metadata.get("gender")
        if isinstance(g, str) and g.strip():
            gender = g.strip().lower()
    if not gender and req.tone:
        t = req.tone.strip().lower()
        if t in ("female", "femeie", "f", "male", "barbat", "bărbat", "m", "neutral"):
            gender = t
    gender_phrase = ""
    if gender in ("female", "femeie", "f"):
        gender_phrase = "a female character (adult woman)"
    elif gender in ("male", "barbat", "bărbat", "m"):
        gender_phrase = "a male character (adult man)"
    else:
        gender_phrase = "a person"
    parts: list[str] = []
    parts.append(
        "VIDEO TOPIC (the subject the video will speak about — your "
        "image prompt MUST visually frame this topic; do NOT substitute "
        "a different subject):\n"
        "<<<BRIEF_START>>>\n"
        f"{brief}\n"
        "<<<BRIEF_END>>>"
    )
    parts.append(f"CHARACTER: {gender_phrase}. Frame as front-facing medium close-up; mouth must be unobstructed (a lipsync model will animate it).")
    parts.append(
        "Now write the single-line English image prompt. Return EXACTLY:\n"
        "{\n"
        f'  "spoken_language": "{(req.language or "en").strip().lower()}",\n'
        '  "script": "<single-line English image prompt — background, '
        'outfit, pose, lighting, render style>"\n'
        "}\n"
        "No markdown fences. No prose outside the braces."
    )
    return "\n\n".join(parts)


# Phase 20 iter 2 — human-readable language labels used to reinforce
# the spoken-language constraint at the top of the user prompt.
_LANG_LABELS: dict[str, str] = {
    "ro": "Romanian (Română)",
    "en": "English",
    "es": "Spanish (Español)",
    "fr": "French (Français)",
    "de": "German (Deutsch)",
    "it": "Italian (Italiano)",
    "pt": "Portuguese (Português)",
    "pl": "Polish (Polski)",
    "hu": "Hungarian (Magyar)",
}


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
) -> tuple[str, str, str, str, float, dict[str, Any]]:
    """Forgiving parser: prefer JSON, fall back to deterministic
    sentence/paragraph segmentation. Always returns a structured tuple
    of (hook, body, cta, full_script, estimated_duration_seconds,
    cinematic) — the last element holds the cinematic JSON when the
    model produced it, otherwise an empty dict.
    """
    data = _safe_json(raw)
    target = float(req.target_duration_seconds)
    cinematic: dict[str, Any] = {}
    if isinstance(data, dict):
        # Phase 21 — scene_plan shape. When the request asked for a
        # plan, the model returns ``{"spoken_language": "...",
        # "scenes": [...]}``; we stash the scenes list in cinematic
        # under the "scenes" key so the API layer can lift it onto
        # the response. Hook/body/cta are derived from the first /
        # mid / last spoken_text so the back-compat fields stay non-empty.
        scenes = data.get("scenes") or data.get("scene_list") or data.get("plan")
        if isinstance(scenes, list) and scenes and (req.mode or "") == "scene_plan":
            # Phase 21 iter 2 — normalise heterogeneous LLM output to
            # the SceneSpec shape. Models frequently use
            # ``visual_duration_seconds`` / ``duration_seconds`` instead
            # of ``duration_s``; omit ``scene_number``; omit ``kind``.
            # Auto-populate + infer from text where possible so the
            # operator gets a usable plan without manual fix-up.
            scenes = _normalise_scenes_list(scenes, req)
            spoken = [
                _coerce_str(s.get("spoken_text")) for s in scenes
                if isinstance(s, dict)
            ]
            spoken = [s for s in spoken if s]
            full_text = "\n\n".join(spoken)
            if len(spoken) >= 3:
                hook = spoken[0]
                cta = spoken[-1]
                body = "\n\n".join(spoken[1:-1])
            elif len(spoken) == 2:
                hook, body, cta = spoken[0], "", spoken[1]
            else:
                hook = spoken[0] if spoken else ""
                body = ""
                cta = ""
            total = sum(
                float(s.get("duration_s") or 0)
                for s in scenes if isinstance(s, dict)
            ) or target
            cinematic = {"scenes": scenes, "spoken_language": data.get("spoken_language")}
            return hook, body, cta, full_text, total, cinematic
        # Phase 20 — cinematic JSON shape detection. If the model
        # returned the scene-by-scene template, derive hook/body/cta
        # from the scene_list + full_voiceover_text so the existing
        # editor / voice / lipsync stages still get the strings they
        # expect. Preserve the full structure in ``cinematic`` for
        # downstream stages that want scene-level visuals.
        scene_list = data.get("scene_list")
        full_vo = _coerce_str(data.get("full_voiceover_text"))
        if isinstance(scene_list, list) and scene_list:
            cinematic = data
            hook, body, cta, full_script = _derive_segments_from_scenes(
                scene_list, full_vo
            )
            est = data.get("estimated_duration_seconds")
            try:
                est_dur = float(est) if est is not None else target
            except (TypeError, ValueError):
                est_dur = target
            return hook, body, cta, full_script, est_dur, cinematic

        # Legacy hook/body/cta shape — kept for back-compat with older
        # operator overrides and the template provider.
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
            return hook, body, cta, full_script, est_dur, cinematic

        # Phase 20 iter 2 — many models ignore the cinematic template
        # when the brief is short and fall back to a flat shape like
        # ``{"script": "<natural-language story>"}`` or
        # ``{"scenariu": "<text>"}`` / ``{"full_voiceover_text": "..."}``.
        # Treat any of these single-string-value fields as the spoken
        # script so the operator sees readable text in the preview
        # instead of raw JSON.
        for key in (
            "full_voiceover_text", "voiceover", "voice_over",
            "script", "scenariu", "scenario", "story",
            "narrative", "text", "content", "spoken_text",
        ):
            raw_val = data.get(key)
            if isinstance(raw_val, str) and raw_val.strip():
                full_script = raw_val.strip()
                hook, body, cta = _segment_plain_text(full_script)
                return hook, body, cta, full_script, target, cinematic
        # Generic fallback: pick the longest string field in the JSON.
        # Avoids "raw JSON in UI" when the model uses an unexpected key.
        longest = ""
        for value in data.values():
            if isinstance(value, str) and len(value.strip()) > len(longest):
                longest = value.strip()
        if longest:
            hook, body, cta = _segment_plain_text(longest)
            return hook, body, cta, longest, target, cinematic

    # Fallback: deterministic segmentation of the raw text.
    text = raw.strip()
    if not text:
        return ("", "", "", "", target, cinematic)
    hook, body, cta = _segment_plain_text(text)
    full_script = "\n\n".join(p for p in (hook, body, cta) if p)
    return hook, body, cta, full_script, target, cinematic


def _segment_plain_text(text: str) -> tuple[str, str, str]:
    """Split a free-form string into (hook, body, cta) using paragraph
    and sentence boundaries. Used both by the raw-text fallback and by
    the JSON path when the model returns a single-string-value shape
    like ``{"script": "<story>"}`` — we want hook/body/cta filled even
    then so the downstream stages don't end up with an empty hook.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) >= 3:
        return paragraphs[0], "\n\n".join(paragraphs[1:-1]), paragraphs[-1]
    if len(paragraphs) == 2:
        return paragraphs[0], paragraphs[1], ""
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[\.\!\?])\s+", paragraphs[0] if paragraphs else text)
        if s.strip()
    ]
    if len(sentences) >= 3:
        return sentences[0], " ".join(sentences[1:-1]), sentences[-1]
    if len(sentences) == 2:
        return sentences[0], sentences[1], ""
    return text, "", ""


def _derive_segments_from_scenes(
    scene_list: list[Any], full_vo: str
) -> tuple[str, str, str, str]:
    """Phase 20 — map the cinematic scene_list to (hook, body, cta,
    full_script) so the downstream voice/editor/lipsync stages keep
    working without changes. The hook is the first scene's spoken_text,
    the cta is the last scene's spoken_text, the body is everything in
    between joined by blank lines. full_script prefers the model's
    own ``full_voiceover_text`` (more natural for TTS than concatenated
    scene strings) and falls back to the joined scene texts.
    """
    spoken: list[str] = []
    for scene in scene_list:
        if not isinstance(scene, dict):
            continue
        text = _coerce_str(scene.get("spoken_text"))
        if text:
            spoken.append(text)
    if not spoken:
        # Scene list was present but every spoken_text was empty —
        # fall back to the voiceover field.
        return full_vo, "", "", full_vo
    if len(spoken) == 1:
        return spoken[0], "", "", full_vo or spoken[0]
    if len(spoken) == 2:
        return spoken[0], "", spoken[1], full_vo or "\n\n".join(spoken)
    hook = spoken[0]
    cta = spoken[-1]
    body = "\n\n".join(spoken[1:-1])
    full_script = full_vo or "\n\n".join(spoken)
    return hook, body, cta, full_script


def _coerce_str(v: Any) -> str:
    if isinstance(v, str):
        return v.strip()
    if v is None:
        return ""
    return str(v).strip()

# Scriptwriter Agent

Generates a hook-driven, duration-bounded script via an LLM backend.

**Status:** to be implemented in Phase 1 (minimal) → Phase 2 (with policy classifier).

## Backend

Default: local vLLM running Llama-3.1-8B-Instruct. Env-driven (`LLM_BACKEND`, `LLM_MODEL_ID`, `LLM_ENDPOINT`).

A future adapter pattern (mirroring lip-sync) is anticipated when paid-API fallbacks (Claude, OpenAI) become useful — they remain optional and off by default.

## Inputs

- Brief: topic, tone, duration, language.
- Persona: which on-screen character is speaking.
- Banned-words list from `configs/policies/banned_topics.yaml`.

## Outputs

- `script.json`:
  ```json
  {
    "language": "en",
    "estimated_duration_sec": 28,
    "scenes": [
      { "kind": "hook",  "text": "...", "ssml": "...", "duration_hint_sec": 4 },
      { "kind": "body",  "text": "...", "ssml": "...", "duration_hint_sec": 20 },
      { "kind": "cta",   "text": "...", "ssml": "...", "duration_hint_sec": 4 }
    ]
  }
  ```

## KPIs

- Duration adherence ±5%.
- Banned-content classifier score = 0.
- Readability inside configured band.

## Hard rules

- Brief is untrusted; system prompt is isolated.
- Output runs through the policy classifier before returning.

# Ollama scriptwriter runtime (Phase 6C → Phase 8G real generation)

Phase 5B added `/api/v1/script/generate` driving the existing
`agents/scriptwriter` registry. The default backend is `template`
(dependency-free, deterministic). **Phase 8G implemented the real
`OllamaProvider.generate()` body** — this runbook covers what an
operator needs to flip to **real local LLM** generation via Ollama with
`qwen3.6` as preferred and `qwen3:8b` as fallback.

## Phase 8G — real generation surface

The provider now does a real HTTP call via stdlib `urllib.request`
(no new pip deps). It:

1. Lazy-checks the daemon at `OLLAMA_BASE_URL/api/tags` for healthcheck.
2. POSTs to `OLLAMA_BASE_URL/api/chat` with `format: "json"` and a
   bounded `num_predict=800`.
3. Tries the preferred model first; on `404 model not found` retries
   with `OLLAMA_FALLBACK_MODEL`.
4. Parses the response as JSON; if the model ignored the JSON-mode
   instruction, falls back to deterministic sentence/paragraph
   segmentation so downstream stages always get a structured
   ScriptResult.
5. Maps daemon/network errors to categorised 503 codes
   (`script_provider_unreachable` / `script_provider_disabled` /
   `script_generation_failed`) — never crashes.

Verified live against `qwen2.5:7b-instruct` on a host-side Ollama
daemon — the response parsed cleanly with `json_parsed=true`.

### From-Docker reachability

When the backend runs in Docker (alt-port stack on `:8001`) and the
Ollama daemon runs on the host (e.g. another stack's
`ai-home-ollama` exposing `0.0.0.0:11434`), `OLLAMA_BASE_URL=http://localhost:11434`
**will not work** from inside the container. Set it to the Docker
default-bridge gateway:

```
OLLAMA_BASE_URL=http://172.17.0.1:11434
```

(On Docker Desktop / macOS / Windows, `host.docker.internal` works too.)

## Boundaries

- No external OpenAI/Anthropic API calls. Those providers stay
  `not_implemented` unless their env vars are set AND
  `SCRIPTWRITER_ENABLE_NETWORK_CALLS=true`.
- No API keys in the frontend.
- No model auto-download. `ollama pull qwen3.6` is an explicit operator
  action.
- No GPU dependency on the backend side. (Ollama can be GPU-accelerated
  on the host; that's transparent to the backend, which only speaks
  HTTP to it.)

## Status states surfaced by the backend

`GET /api/v1/providers/llm` lists every backend in the scriptwriter
registry. The Ollama row's status follows the standard `ProviderInfo`
schema:

| API `status` | Meaning |
|---|---|
| `not_implemented` | `SCRIPTWRITER_ENABLE_NETWORK_CALLS=false` — explicit operator gate |
| `configured` | Network calls enabled, model + endpoint set, but reachability not probed |
| `available` | (Reserved — Phase 6C does not run a live ping; status reflects config only) |

The `notes` field carries the exact reason for non-`available` states.

`POST /api/v1/script/generate` maps the runtime states to 503 codes:

| 503 `code` | Reason |
|---|---|
| `script_provider_disabled` | Network calls off + operator picked a network provider |
| `script_provider_unreachable` | Network calls on; provider stub returned `ProviderNotImplementedError` (Ollama server not reachable / model missing) |
| `script_provider_not_configured` | Unknown provider id |
| `script_provider_not_implemented` | Provider exists but generation stub never wired |
| `script_generation_failed` | Defensive: provider threw during generation |

## 1. Install + start Ollama

Ollama is a standalone process. Install per
<https://ollama.com> (binary release, no Python dep).

```bash
# Start the daemon (defaults to http://localhost:11434).
ollama serve
```

Verify it's reachable:

```bash
curl -fsS http://localhost:11434/api/tags
```

## 2. Pull the preferred + fallback models

```bash
ollama pull qwen3.6      # preferred — produces the structured script
ollama pull qwen3:8b     # fallback — smaller, faster, lower quality
```

> The project's `SCRIPTWRITER_MODEL=qwen3.6` is the canonical preferred
> name. `qwen3.6:7b` is **never** used; a CI test pins that string is
> absent from production code (see
> `test_phase3g_scriptwriter_contracts.py::test_qwen36_7b_is_not_hardcoded_anywhere`).

### Phase 11G — lightweight alternative: `qwen2.5:7b`

If `qwen3.6` (~24 GB) is too heavy for your hardware or you want a
much faster turnaround during development, override `OLLAMA_MODEL`
to a lighter Qwen variant. The application has no built-in
preference — it uses whatever `OLLAMA_MODEL` resolves to on the
operator-controlled daemon.

```bash
ollama pull qwen2.5:7b-instruct   # ~4.6 GB, instruction-tuned
export OLLAMA_MODEL=qwen2.5:7b-instruct
```

> **The application never auto-pulls.** Every `ollama pull` must be
> explicitly run by the operator on the Ollama host. The Makefile
> intentionally exposes `make ollama-status` / `make ollama-models`
> for diagnostics, but no `make ollama-pull-*` target runs without
> a confirmed argument.

Verify availability:

```bash
curl -fsS http://localhost:11434/api/tags \
  | python -c 'import json,sys; print([m["name"] for m in json.load(sys.stdin)["models"]])'
```

You should see `qwen3.6` and `qwen3:8b` in the list.

## 3. Configure env vars

Append to `.env` (these all have working defaults in `.env.example`):

```bash
# Switch the scriptwriter to Ollama.
SCRIPTWRITER_BACKEND=ollama
SCRIPTWRITER_MODEL=qwen3.6
SCRIPTWRITER_FALLBACK_MODEL=qwen3:8b

# Explicit operator-controlled gate. Defaults to false.
SCRIPTWRITER_ENABLE_NETWORK_CALLS=true

# Where the Ollama daemon listens.
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.6
OLLAMA_FALLBACK_MODEL=qwen3:8b
```

Restart the backend (in venv: `uvicorn app.main:app --reload`; in
Docker: `make docker-light-down && make docker-light-up`).

## 4. Confirm provider status

```bash
curl -fsS http://localhost:8000/api/v1/providers/llm \
  | python -m json.tool
```

Expect the `ollama` row to flip to `configured` once the env vars are
set. If `SCRIPTWRITER_ENABLE_NETWORK_CALLS` is missing or `false`, the
row stays at `not_implemented` with a clear notes line.

## 5. Call /api/v1/script/generate

```bash
curl -fsS -X POST http://localhost:8000/api/v1/script/generate \
  -H "Content-Type: application/json" \
  -d '{
        "brief": "Three calming bedtime habits for better sleep.",
        "target_duration_seconds": 30,
        "provider_id": "ollama",
        "language": "en"
      }'
```

Expected on success (HTTP 201):

```json
{
  "status": "generated",
  "provider_id": "ollama",
  "model": "qwen3.6",
  "hook": "...",
  "body": "...",
  "cta": "...",
  "full_script": "...",
  "estimated_duration_seconds": 28.5,
  "language": "en",
  "artifact_id": null,
  "message": "Preview-only; copy into Create Job to register an artifact."
}
```

If you see HTTP 503 instead, the `detail.code` tells you which gate
fired:

| Code | Fix |
|---|---|
| `script_provider_disabled` | Set `SCRIPTWRITER_ENABLE_NETWORK_CALLS=true` in `.env` and restart |
| `script_provider_unreachable` | Ollama daemon not running, or `OLLAMA_BASE_URL` wrong. `curl $OLLAMA_BASE_URL/api/tags` to debug. |
| `script_model_missing` | Daemon is reachable but the configured `OLLAMA_MODEL` is not pulled. Run `ollama pull <model>` on the Ollama host (Phase 8G-2 split this out from `script_provider_unreachable` so the UI can give a precise recovery instruction). |
| `script_generation_failed` | Daemon responded but the body was malformed. Check the daemon's logs. |
| `script_provider_not_configured` | `provider_id` is a typo |

## 6. Use Generate Script in the UI

1. Open `/jobs/new`.
2. Voice mode = TTS.
3. Fill the brief.
4. In **Providers**, pick `Ollama` as the script LLM (or set it as your
   per-category default in Settings first).
5. Click **Generate script**. The full script appears in the textarea;
   edit, then submit.

The Logs sidebar tab records `script-generate start` → `succeeded` /
`<code>` so you can audit which path actually ran.

## 7. Error-message dictionary

| UI shows | Means |
|---|---|
| "Generate script — fill in the brief first." | Local validation, no network call yet |
| "script_provider_disabled: …" | `SCRIPTWRITER_ENABLE_NETWORK_CALLS=false` |
| "script_provider_unreachable: …" | Network calls on but the Ollama daemon is not reachable |
| "script_model_missing: …" | Daemon is reachable but the requested model is not pulled — run `ollama pull <model>` |
| "script_provider_not_configured: …" | Bad `provider_id` |
| "script_provider_not_implemented: …" | Provider exists but stub never wired (Ollama's current state until network is enabled) |
| "script_generation_failed: …" | Defensive — provider raised mid-call. Check backend logs. |

## Docker support

The default light backend image does NOT install or run Ollama. The
runtime is the operator's daemon, reachable over HTTP from the backend
container. If running under Docker:

- **Same-host Ollama**: set `OLLAMA_BASE_URL=http://host.docker.internal:11434`
  and ensure your Docker setup routes the host loopback to the
  container (Docker Desktop: works out of the box; rootless Docker:
  may need `--add-host=host.docker.internal:host-gateway`).
- **Ollama in compose**: the optional `model-llm` service in
  `docker/compose.dev.yml` stays gated by `profiles: ["llm"]`. Enabling
  it would still NOT pull models automatically — `ollama pull qwen3.6`
  remains the operator's job.

GPU acceleration of Ollama is handled by Ollama itself outside this
project. The backend just speaks HTTP.

## Optional real-runtime tests

Tests under `tests/integration/test_phase5b_script_generate.py`
exercise:

- Template provider always returns a structured script.
- Ollama with `SCRIPTWRITER_ENABLE_NETWORK_CALLS=false` → 503
  `script_provider_disabled`.
- Ollama with the flag on but no real client → 503
  `script_provider_unreachable`.
- Unknown provider id → 503 `script_provider_not_configured`.

A real-Ollama generation test isn't part of the default suite — it
needs a reachable daemon + `qwen3.6` model + an explicit opt-in env.
The phase6c readiness test documents the expected stub-skipping
behavior.

## Cross-references

- `backend/app/api/script.py` — endpoint + 503 categorisation.
- `agents/scriptwriter/providers/ollama/provider.py` — Phase 3G stub
  contract.
- `agents/scriptwriter/core/registry.py` — backend resolution.
- `tests/integration/test_phase5b_script_generate.py` — per-state
  assertions.
- `tests/integration/test_phase3g_scriptwriter_contracts.py` — pins
  `qwen3.6:7b` not hardcoded.

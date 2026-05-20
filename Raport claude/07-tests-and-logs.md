# 07 — Tests and logs

## Backend test suite (evidence: `python -m pytest tests/ -q`)
```
926 passed, 12 skipped in 34.43s
```
- 12 skips are runtime smokes gated behind env flags (real Piper / Ollama / SadTalker on host GPU) — expected, documented in each skip reason.
- Identity-pipeline tests present and passing: `test_phase_ig1_comfyui_workflows.py` (11), `test_phase_ig2_identity_generation.py` (incl. real-person reject + public-persona allowed), `test_phase_ig5_compliance_kontext.py` (4: upload gate, moderation gate, Kontext stub `not_configured`, face-score disabled→null).
- Migration drift test `test_phase6b_migrations.py::test_autogenerate_against_head_yields_no_drift` PASSES (models match head 0010 after index alignment).
- API-surface parity test passes → every live `/api/v1` route is documented.

> Caveat: tests run from the host `.venv` against an ephemeral test DB built from models (`init_db`), not against the live Postgres. They prove code/contract correctness, NOT live ComfyUI generation.

## Frontend (evidence)
- `npm run lint` → `✔ No ESLint warnings or errors` (`--max-warnings 0`).
- `npx tsc --noEmit` → clean.
- `npm run build` → NOT RUN this audit (lint+tsc+healthy-container used as proxy). NOT VERIFIED for production build.
- `npm run test` → no frontend unit-test runner configured (Next lint only). NOT VERIFIED.

## Live runtime evidence
- `generate-initial` on Alexandra → real artifact `51e38630-…png`, **1,012,995 bytes, 768×1024**, PNG magic `89 50 4e 47`, DB role=`generated_initial`, provider=`comfyui_local`. End-to-end real render confirmed.
- ComfyUI earlier returned **HTTP 500** on a `_comment` top-level key (`AttributeError: 'str' object has no attribute 'get'` in `execution.validate_prompt`). Evidence: `docker logs aivideo-model-comfyui-1`. The strip-`_`-keys fix IS deployed (running backend `local_wrapper_stub.py:329 return {k:v ... if not str(k).startswith("_")}`) and the subsequent generation succeeded → **bug RESOLVED at runtime**.

## Logs reviewed
- `docker logs aivideo-model-comfyui-1` (the 500 traceback, now resolved).
- `docker compose logs` not dumped wholesale (services healthy). Backend audit log channel `image.audit` emits compliance events (REQUESTED/APPROVED/REFERENCE_SET/…) to stdout.

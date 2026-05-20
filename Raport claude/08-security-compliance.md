# 08 — Security / compliance

## Secrets handling
- `.env` is **gitignored and NOT tracked** (`git check-ignore .env` → ignored; `git ls-files .env` → not tracked). No secret values committed.
- Secret-bearing keys in `.env` (names only, values redacted): `JWT_SECRET`, `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_COMPATIBLE_API_KEY`, `COMPLIANCE_SIGNING_KEY`. These appear empty/placeholder for the API keys in dev.
- `rg 'BEGIN RSA|BEGIN OPENSSH|password=|secret=|api_key='` over tracked non-md source → 3 hits, all config-default assignments (not literal secrets). No private keys in source.
- DB-backed API secrets feature exists (`/api/v1/secrets` + `0005_api_secrets` migration) — values stored server-side, not in code.

## CORS
- `backend/app/core/config.py:32` — `backend_cors_origins` restricted to `localhost:{3000,3001,3010}` + `127.0.0.1` equivalents. Appropriate for dev; **must be widened/locked deliberately for any public deployment** (NOT VERIFIED for prod domain).

## Compliance gates (synthetic-only product rules)
- **Synthetic-only gate** (`character_image_service.assert_synthetic_only`): blocks generation only when `identity.is_real_person == true` (explicit real-person flag), gated by `SYNTHETIC_ONLY_ENFORCED=true`. Verified: a real-person-flagged char → 422; a normal synthetic char (incl. `is_public_persona=true`) is allowed. NOTE: an earlier version wrongly used `is_public_persona` and blocked all characters — corrected this session.
- **Gated upload-reference**: requires `synthetic_attestation=true`, else 422 + audit `CHARACTER_REFERENCE_UPLOAD_BLOCKED`. Uploaded refs land `moderation_status=pending` and CANNOT be promoted to canonical until approved (enforced in set-main/full-body endpoints → 409). Verified by `test_phase_ig5`. **BUT no UI exists** for this flow (see 06) → the safeguard is only reachable via API.
- **Audit events** (`image_audit.py`): REQUESTED/APPROVED/REJECTED, REFERENCE_SET, REFERENCE_UPLOADED/BLOCKED/MODERATED, IDENTITY_DRIFT_WARNING, IMAGE_PROVIDER_FAILURE — emitted to the `image.audit` logger (NOT the DB `compliance_events` table, which is job-scoped). Auditable via logs only → consider persisting for production.
- **Drift scoring** (InsightFace/ArcFace): OFF by default (`FACE_EMBEDDING_ENABLED=false`); returns null when disabled. README flags the **non-commercial license** of InsightFace antelopev2 — a real legal item before commercial use.

## Compliance signing / disclosure
- `COMPLIANCE_SIGNING_KEY` + `compliance` model/events exist for the reel pipeline (AI-disclosure / C2PA flags on jobs). Not re-exercised this audit (DAG stopped) → NOT VERIFIED at runtime.

## Risks
- HIGH: gated-upload + moderation safeguard has no UI → operators may bypass it or it goes unused.
- MEDIUM: image-pipeline audit events are log-only (not durable DB rows) → weaker auditability than the reel pipeline.
- MEDIUM: CORS + public exposure for prod not defined.

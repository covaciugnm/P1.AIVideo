# scripts/

CLI helpers. **Status:** to be implemented as each phase lands.

## Planned scripts

| Path | Purpose |
|---|---|
| `models/download_llm.sh` | Fetch + verify LLM weights. |
| `models/download_tts.sh` | Fetch + verify Piper / XTTS voices. |
| `models/download_sdxl.sh` | Fetch + verify SDXL base + persona LoRA. |
| `models/download_sadtalker.sh` | Fetch + verify SadTalker checkpoints + GFPGAN. |
| `models/download_whisper.sh` | Fetch + verify WhisperX models. |
| `models/build_identity_index.sh` | Build the public-figures CLIP embedding index. |
| `seed_db.sh` | Seed an admin user + sample brief in dev. |
| `e2e_run.sh` | Submit a canned brief and follow it through the pipeline. |
| `compliance_audit.sh` | Export audit-log entries for a date range. |

## Conventions

- Every download script:
  - Prints the license summary and requires `--accept-license` to proceed.
  - Verifies SHA256 against `models/MODEL_CARDS.md`.
  - Refuses to overwrite existing files unless `--force` is passed.
- Every script logs its actions to `audit_log` where applicable.

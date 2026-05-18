# P1.AIVideo Makefile.
# Targets are safe by default — they do not auto-build images, install deps,
# or download model weights. Phase-1+ commands assume you have already run
# the install step described in docs/runbooks/dev-setup.md.

COMPOSE_DEV  := docker compose -f docker/compose.dev.yml
COMPOSE_GPU  := docker compose -f docker/compose.dev.yml -f docker/compose.gpu.yml

.PHONY: demo-jobs docker-tts-ro-build docker-tts-ro-up docker-tts-ro-down \
	docker-tts-ro-logs docker-tts-ro-smoke \
	orchestrator-logs process-demo-jobs phase10a1-worker-test
.PHONY: help up up-gpu down logs ps test test-unit test-integration lint fmt \
        check-env models-check phase1-test phase2-test phase3a-test phase3b-test phase3c-test phase3d-test phase3e-test phase3f-test phase3g-test phase3h-test phase3i-test phase3j-test phase4a-test phase4a2-test phase4b-test phase4d-test phase4e-test phase4f-test phase4f2-test phase4f3-test phase5a-test phase5b-test phase5c-test phase6a-test phase6b-test phase6c-test phase6d-test phase7a-test phase7b-test phase7c-test phase7d-test phase7e-test phase8a-test phase8b-test phase8c-test phase8d-test phase8e-test phase8f1-test phase8g-test phase8g2-test \
        db-migrate db-upgrade db-downgrade db-current db-history runtime-readiness-check \
        frontend-install frontend-lint frontend-build frontend-check \
        docker-config-check docker-light-build docker-light-up docker-light-down docker-light-logs docker-light-smoke docker-light-check docker-light-stop docker-light-start scenario-jobs scenario-jobs-check \
        docker-gpu-config-check docker-gpu-smoke docker-gpu-build docker-gpu-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Compose lifecycle. None of these run `--build` automatically. To rebuild
# images, run `docker compose ... build <service>` explicitly.
# ---------------------------------------------------------------------------

up: ## Start the dev stack (CPU)
	$(COMPOSE_DEV) up -d

up-gpu: ## Start the dev stack with GPU overlay
	$(COMPOSE_GPU) up -d

down: ## Stop the stack
	$(COMPOSE_DEV) down

logs: ## Tail logs for all services
	$(COMPOSE_DEV) logs -f --tail=200

ps: ## List running services
	$(COMPOSE_DEV) ps

# ---------------------------------------------------------------------------
# Tests. Assumes you've installed the Phase 1 Python deps:
#   pip install -e ./backend[dev] -e ./agents[dev]
# See docs/runbooks/dev-setup.md.
# ---------------------------------------------------------------------------

test: ## Run all tests
	pytest -v

phase1-test: ## Run the Phase 1 integration test only
	pytest -v tests/integration/test_phase1_metadata_flow.py

phase2-test: ## Run the Phase 2 no-op DAG integration test only
	pytest -v tests/integration/test_phase2_noop_dag.py

phase3a-test: ## Run the Phase 3A provider-healthcheck tests only
	pytest -v tests/integration/test_phase3a_provider_healthchecks.py

phase3b-test: ## Run the Phase 3B narrow (Piper-only) integration tests
	pytest -v tests/integration/test_phase3b_piper.py

phase3c-test: ## Run the Phase 3C voice-mode routing + provided-audio tests
	pytest -v tests/integration/test_phase3c_voice_modes.py

phase3d-test: ## Run the Phase 3D audio validation + artifact registry tests
	pytest -v tests/integration/test_phase3d_audio_artifacts.py

phase3e-test: ## Run the Phase 3E image validation + face artifact tests
	pytest -v tests/integration/test_phase3e_image_artifacts.py

phase3f-test: ## Run the Phase 3F packaging contract + ArtifactType enum tests
	pytest -v tests/integration/test_phase3f_packaging_contracts.py

phase3g-test: ## Run the Phase 3G scriptwriter contract + provider registry tests
	pytest -v tests/integration/test_phase3g_scriptwriter_contracts.py

phase3h-test: ## Run the Phase 3H editor edit-plan tests
	pytest -v tests/integration/test_phase3h_editor_plan.py

phase3i-test: ## Run the Phase 3I QC report tests
	pytest -v tests/integration/test_phase3i_qc_report.py

phase3j-test: ## Run the Phase 3J publisher / final_export tests
	pytest -v tests/integration/test_phase3j_publisher_export.py

phase4a-test: ## Run the Phase 4A job-view API tests
	pytest -v tests/integration/test_phase4a_job_api.py

phase4a2-test: ## Run the Phase 4A-2 upload intake + from-inputs API tests
	pytest -v tests/integration/test_phase4a2_upload_intake_api.py

phase4b-test: ## Run the Phase 4B backend meta endpoints + frontend lint+build
	pytest -v tests/integration/test_phase4b_meta_endpoints.py
	$(MAKE) frontend-check

phase4d-test: ## Phase 4D — frontend lint + build (sidebar + settings + logs); backend regression
	$(MAKE) frontend-check
	pytest -v tests/integration/test_phase4b_meta_endpoints.py

phase4e-test: ## Phase 4E — frontend lint + build + Phase 4E PATCH/DELETE tests + Phase 4B meta tests
	$(MAKE) frontend-check
	pytest -v tests/integration/test_phase4b_meta_endpoints.py tests/integration/test_phase4e_job_patch_delete.py

phase4f-test: ## Phase 4F — providers/TTS/artifact-content/upload-formats; ffmpeg test auto-skipped if missing
	$(MAKE) frontend-check
	pytest -v tests/integration/test_phase4f_providers_tts_artifacts.py

phase4f2-test: ## Phase 4F-2 — Phase 4A API completeness backfill (summary, JobSummary flags, JobDetail aggregate, JobProgress flat lists, status filter)
	pytest -v tests/integration/test_phase4f2_job_api_backfill.py

phase4f3-test: ## Phase 4F-3 — frontend consumes Phase 4F-2 backfill (lint + build) + Phase 4F-2 backend tests
	$(MAKE) frontend-check
	pytest -v tests/integration/test_phase4f2_job_api_backfill.py

phase5a-test: ## Phase 5A — real Piper TTS gating (runtime/assets categorisation). Real synthesis tests auto-skip without piper-tts.
	pytest -v tests/integration/test_phase5a_tts_runtime.py

phase5b-test: ## Phase 5B — /api/v1/script/generate (Ollama gated; template always works)
	pytest -v tests/integration/test_phase5b_script_generate.py

phase5c-test: ## Phase 5C — /api/v1/audio/fit-check classification
	pytest -v tests/integration/test_phase5c_audio_fit.py

phase6a-test: ## Phase 6A — /api/v1/video/generate metadata-only contract
	pytest -v tests/integration/test_phase6a_video_contract.py

phase6b-test: ## Phase 6B — Alembic migration smoke + initial-migration drift guard
	pytest -v tests/integration/test_phase6b_migrations.py

phase6c-test: ## Phase 6C — Piper/Ollama runtime-readiness gating + provider catalog shape. Real Piper/Ollama tests auto-skip without RUN_REAL_*_SMOKE=1.
	pytest -v tests/integration/test_phase6c_runtime_readiness.py

phase6d-test: ## Phase 6D — multi-category provider registry + ProviderSelection extensions
	pytest -v tests/integration/test_phase6d_provider_registry.py

phase7a-test: ## Phase 7A — GPU isolation invariants + video catalog gating (no real inference, no GPU required)
	pytest -v tests/integration/test_phase7a_gpu_planning.py

phase7b-test: ## Phase 7B — SadTalker adapter hardening (readiness + categorised /video/generate errors; no real inference)
	pytest -v tests/integration/test_phase7b_sadtalker_adapter.py

phase7c-test: ## Phase 7C — GPU image / runtime for SadTalker readiness (static file + compose merge checks; no GPU required)
	pytest -v tests/integration/test_phase7c_gpu_image.py

phase7d-test: ## Phase 7D — SadTalker real-inference gate + artifact registration (success path monkey-patched; real smoke auto-skipped without RUN_REAL_SADTALKER_SMOKE=1)
	pytest -v tests/integration/test_phase7d_sadtalker_inference.py

phase7e-test: ## Phase 7E — lipsync DAG stage integration (provider_selection routing, categorised StageRejection, monkey-patched real-inference hook)
	pytest -v tests/integration/test_phase7e_pipeline_integration.py

phase8a-test: ## Phase 8A — video artifact preview + safe content serving + bounded ffprobe helper
	pytest -v tests/integration/test_phase8a_video_artifact_preview.py

phase8b-test: ## Phase 8B — real ffmpeg final-export service + /api/v1/export/finalize (real success path needs ffmpeg + ffprobe on PATH)
	pytest -v tests/integration/test_phase8b_final_export.py

phase8c-test: ## Phase 8C — real media QC + /api/v1/qc/inspect (real success path needs ffmpeg + ffprobe on PATH)
	pytest -v tests/integration/test_phase8c_real_media_qc.py

phase8d-test: ## Phase 8D — job cancel + retry + recovery_metadata
	pytest -v tests/integration/test_phase8d_job_recovery.py

phase8e-test: ## Phase 8E — /jobs/from-inputs accepts provider_selection (regression: extra_forbidden bug)
	pytest -v tests/integration/test_phase8e_provider_selection_from_inputs.py

phase8f1-test: ## Phase 8F-1 — strict Create Job contract for provider_selection (all 4 routes + nested extra_forbidden + summary expose)
	pytest -v tests/integration/test_phase8f1_create_job_provider_selection.py

phase8g-test: ## Phase 8G — real Ollama generation + Piper opt-in (mocked + opt-in real smokes auto-skip)
	pytest -v tests/integration/test_phase8g_ollama_generation.py tests/integration/test_phase8g_piper_generation.py

phase8g2-test: ## Phase 8G-2 — DAG voice → real Piper + script_model_missing distinct code
	pytest -v tests/integration/test_phase8g2_voice_stage_piper.py tests/integration/test_phase8g2_script_model_missing.py

docker-light-stop: ## Phase 8E — stop containers WITHOUT removing volumes. Data safe.
	@$(COMPOSE_DEV) stop backend orchestrator frontend postgres redis 2>&1 | tail -10

docker-light-start: ## Phase 8E — start the light stack on alt ports (preserves existing volumes).
	@test -f .env || (echo "ERROR: .env missing. Run: cp .env.example .env" && exit 1)
	@POSTGRES_PORT=$${POSTGRES_PORT:-5433} \
		BACKEND_PORT=$${BACKEND_PORT:-8001} \
		FRONTEND_PORT=$${FRONTEND_PORT:-3010} \
		NEXT_PUBLIC_API_BASE_URL=$${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8001} \
		$(COMPOSE_DEV) up -d postgres redis backend orchestrator frontend

scenario-jobs: ## Phase 8E — seed 8 scenario jobs against a running backend. Honours BACKEND_BASE_URL (default http://localhost:8001).
	@BACKEND_BASE_URL=$${BACKEND_BASE_URL:-http://localhost:8001} \
		python3 scripts/create_scenario_jobs.py

scenario-jobs-check: ## Phase 8E — sanity-check that scenario jobs exist in the running backend's job list.
	@curl -fsS $${BACKEND_BASE_URL:-http://localhost:8001}/api/v1/jobs \
		| python3 -c "import json,sys;jobs=json.load(sys.stdin);scn=[j for j in jobs if isinstance(j.get('brief'),str) and j['brief'].startswith('Scenario ')];print(f'scenario jobs visible: {len(scn)}');[print(f'  - {j[\"brief\"][:80]}') for j in scn[:20]]"

demo-jobs: ## Phase 10A-0 — idempotently seed the persistent "Demo —" matrix.
	@BACKEND_BASE_URL=$${BACKEND_BASE_URL:-http://localhost:8001} \
		python3 scripts/create_scenario_jobs.py --demo

orchestrator-logs: ## Phase 10A-1 — tail orchestrator worker logs.
	@$(COMPOSE_DEV) logs --tail=200 -f orchestrator

process-demo-jobs: ## Phase 10A-1 — wait until every "Demo —" job leaves pending_compliance (max 120s).
	@BACKEND_BASE_URL=$${BACKEND_BASE_URL:-http://localhost:8001} \
		python3 -c "import time,sys,urllib.request,json; \
base=__import__('os').environ.get('BACKEND_BASE_URL','http://localhost:8001'); \
deadline=time.time()+120; \
fmt=lambda j: f\"  {j['id'][:8]}.. {j['status']:>22}  {j['brief']}\"; \
last=[]; \
import urllib.request as r; \
go=lambda: json.loads(r.urlopen(f'{base}/api/v1/jobs', timeout=5).read()); \
\
def report(jobs): \
    demos=[j for j in jobs if (j.get('brief') or '').startswith('Demo —')]; \
    demos.sort(key=lambda j: j['brief']); \
    pending=[j for j in demos if j['status']=='pending_compliance']; \
    print(f'  pending={len(pending)}/{len(demos)} demos'); \
    return pending; \
while time.time() < deadline: \
    jobs=go(); pending=report(jobs); \
    if not pending: break; \
    time.sleep(3); \
else: \
    print('TIMEOUT — demo jobs still pending after 120s', file=sys.stderr); sys.exit(2); \
print('OK — all demo jobs left pending_compliance.'); \
[print(fmt(j)) for j in sorted([j for j in jobs if (j.get('brief') or '').startswith('Demo —')], key=lambda j: j['brief'])]"

phase10a1-worker-test: ## Phase 10A-1 — run the orchestrator worker test file.
	pytest -q tests/integration/test_phase10a1_orchestrator_worker.py

# ----- Phase 10A-1 — optional F5TTS-Ro Romanian TTS wrapper --------------
docker-tts-ro-build: ## Build the optional F5TTS-Ro wrapper image.
	@BACKEND_PORT=$${BACKEND_PORT:-8001} FRONTEND_PORT=$${FRONTEND_PORT:-3010} \
		POSTGRES_PORT=$${POSTGRES_PORT:-5433} REDIS_PORT=$${REDIS_PORT:-6380} \
		NEXT_PUBLIC_API_BASE_URL=$${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8001} \
		$(COMPOSE_DEV) --profile tts-ro build model-tts-ro

docker-tts-ro-up: ## Start the optional F5TTS-Ro wrapper. Sets F5TTS_RO_BASE_URL automatically for the backend on next restart.
	@BACKEND_PORT=$${BACKEND_PORT:-8001} FRONTEND_PORT=$${FRONTEND_PORT:-3010} \
		POSTGRES_PORT=$${POSTGRES_PORT:-5433} REDIS_PORT=$${REDIS_PORT:-6380} \
		NEXT_PUBLIC_API_BASE_URL=$${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8001} \
		$(COMPOSE_DEV) --profile tts-ro up -d model-tts-ro

docker-tts-ro-down: ## Stop the optional F5TTS-Ro wrapper. Does NOT delete volumes.
	@BACKEND_PORT=$${BACKEND_PORT:-8001} FRONTEND_PORT=$${FRONTEND_PORT:-3010} \
		POSTGRES_PORT=$${POSTGRES_PORT:-5433} REDIS_PORT=$${REDIS_PORT:-6380} \
		NEXT_PUBLIC_API_BASE_URL=$${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8001} \
		$(COMPOSE_DEV) --profile tts-ro stop model-tts-ro

docker-tts-ro-logs: ## Tail F5TTS-Ro wrapper logs.
	@$(COMPOSE_DEV) logs -f model-tts-ro

docker-tts-ro-smoke: ## Probe /health on the F5TTS-Ro wrapper without touching weights.
	@curl -fsS $${F5TTS_RO_BASE_URL:-http://localhost:8061}/health \
		| python3 -m json.tool

# ----- Phase 10B — SadTalker GPU wrapper (heavy, opt-in, --profile sadtalker) -
docker-sadtalker-build: ## Phase 10B — build the SadTalker GPU wrapper image (~8 GB, requires NVIDIA Container Toolkit).
	@BACKEND_PORT=$${BACKEND_PORT:-8001} FRONTEND_PORT=$${FRONTEND_PORT:-3010} \
		POSTGRES_PORT=$${POSTGRES_PORT:-5433} REDIS_PORT=$${REDIS_PORT:-6380} \
		NEXT_PUBLIC_API_BASE_URL=$${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8001} \
		$(COMPOSE_DEV) --profile sadtalker build model-sadtalker

docker-sadtalker-up: ## Phase 10B — start the SadTalker GPU wrapper. Set SADTALKER_BASE_URL on the backend afterwards.
	@BACKEND_PORT=$${BACKEND_PORT:-8001} FRONTEND_PORT=$${FRONTEND_PORT:-3010} \
		POSTGRES_PORT=$${POSTGRES_PORT:-5433} REDIS_PORT=$${REDIS_PORT:-6380} \
		NEXT_PUBLIC_API_BASE_URL=$${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8001} \
		$(COMPOSE_DEV) --profile sadtalker up -d model-sadtalker

docker-sadtalker-down: ## Phase 10B — stop the SadTalker GPU wrapper. Does NOT delete volumes.
	@BACKEND_PORT=$${BACKEND_PORT:-8001} FRONTEND_PORT=$${FRONTEND_PORT:-3010} \
		POSTGRES_PORT=$${POSTGRES_PORT:-5433} REDIS_PORT=$${REDIS_PORT:-6380} \
		NEXT_PUBLIC_API_BASE_URL=$${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8001} \
		$(COMPOSE_DEV) --profile sadtalker stop model-sadtalker

docker-sadtalker-logs: ## Phase 10B — tail SadTalker wrapper logs.
	@$(COMPOSE_DEV) logs -f model-sadtalker

docker-sadtalker-smoke: ## Phase 10B — probe /health on the SadTalker wrapper.
	@curl -fsS $${SADTALKER_BASE_URL:-http://localhost:8062}/health \
		| python3 -m json.tool

# ----- Phase 12W — Image generation GPU wrappers (FLUX / SDXL / SD3.5) -------
docker-sdxl-build: ## Phase 12W — build the SDXL wrapper image (~9 GB, requires NVIDIA Container Toolkit).
	@docker compose --env-file .env -f docker/compose.dev.yml --profile sdxl build model-sdxl

docker-sdxl-up: ## Phase 12W — start the SDXL wrapper. Set SDXL_LOCAL_BASE_URL on the backend afterwards.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile sdxl up -d model-sdxl

docker-sdxl-down: ## Phase 12W — stop the SDXL wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile sdxl stop model-sdxl

docker-sdxl-logs: ## Phase 12W — tail SDXL wrapper logs.
	@docker compose --env-file .env -f docker/compose.dev.yml logs -f model-sdxl

docker-sdxl-smoke: ## Phase 12W — probe /health on the SDXL wrapper.
	@curl -fsS $${SDXL_LOCAL_BASE_URL:-http://localhost:8063}/health | python3 -m json.tool

docker-flux-build: ## Phase 12W — build the FLUX wrapper image (~12 GB).
	@docker compose --env-file .env -f docker/compose.dev.yml --profile flux build model-flux

docker-flux-up: ## Phase 12W — start the FLUX wrapper. Operator accepts BFL license on HF + places weights under models/image/flux/.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile flux up -d model-flux

docker-flux-down: ## Phase 12W — stop the FLUX wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile flux stop model-flux

docker-flux-logs: ## Phase 12W — tail FLUX wrapper logs.
	@docker compose --env-file .env -f docker/compose.dev.yml logs -f model-flux

docker-flux-smoke: ## Phase 12W — probe /health on the FLUX wrapper.
	@curl -fsS $${FLUX_LOCAL_BASE_URL:-http://localhost:8064}/health | python3 -m json.tool

docker-sd35-build: ## Phase 12W — build the SD3.5 wrapper image (~10 GB).
	@docker compose --env-file .env -f docker/compose.dev.yml --profile sd35 build model-sd35

docker-sd35-up: ## Phase 12W — start the SD3.5 wrapper. Operator accepts Stability license + places weights.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile sd35 up -d model-sd35

docker-sd35-down: ## Phase 12W — stop the SD3.5 wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile sd35 stop model-sd35

docker-sd35-logs: ## Phase 12W — tail SD3.5 wrapper logs.
	@docker compose --env-file .env -f docker/compose.dev.yml logs -f model-sd35

docker-sd35-smoke: ## Phase 12W — probe /health on the SD3.5 wrapper.
	@curl -fsS $${SD35_LOCAL_BASE_URL:-http://localhost:8065}/health | python3 -m json.tool

docker-comfyui-build: ## Phase 12W — build the ComfyUI wrapper image (~10 GB).
	@docker compose --env-file .env -f docker/compose.dev.yml --profile comfyui build model-comfyui

docker-comfyui-up: ## Phase 12W — start the ComfyUI wrapper. Replaces the host install.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile comfyui up -d model-comfyui

docker-comfyui-down: ## Phase 12W — stop the ComfyUI wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile comfyui stop model-comfyui

docker-comfyui-logs: ## Phase 12W — tail ComfyUI wrapper logs.
	@docker compose --env-file .env -f docker/compose.dev.yml logs -f model-comfyui

docker-comfyui-smoke: ## Phase 12W — probe /system_stats on the ComfyUI wrapper.
	@curl -fsS $${COMFYUI_BASE_URL:-http://localhost:8066}/system_stats | python3 -m json.tool

docker-a1111-build: ## Phase 12W — build the A1111 wrapper image (~12 GB, Python 3.10 + cu128 + pre-cloned repos).
	@docker compose --env-file .env -f docker/compose.dev.yml --profile a1111 build model-a1111

docker-a1111-up: ## Phase 12W — start the A1111 wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile a1111 up -d model-a1111

docker-a1111-down: ## Phase 12W — stop the A1111 wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile a1111 stop model-a1111

docker-a1111-logs: ## Phase 12W — tail A1111 wrapper logs.
	@docker compose --env-file .env -f docker/compose.dev.yml logs -f model-a1111

docker-a1111-smoke: ## Phase 12W — probe /sdapi/v1/sd-models on the A1111 wrapper.
	@curl -fsS $${A1111_BASE_URL:-http://localhost:8067}/sdapi/v1/sd-models | python3 -m json.tool | head -30

# ----- Phase 12Y — open-source lip-sync video wrappers -----------------------
docker-wav2lip-build: ## Phase 12Y — build the Wav2Lip wrapper image (~8 GB).
	@docker compose --env-file .env -f docker/compose.dev.yml --profile wav2lip build model-wav2lip

docker-wav2lip-up: ## Phase 12Y — start Wav2Lip wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile wav2lip up -d model-wav2lip

docker-wav2lip-down: ## Phase 12Y — stop Wav2Lip wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile wav2lip stop model-wav2lip

docker-wav2lip-logs: ## Phase 12Y — tail Wav2Lip wrapper logs.
	@docker compose --env-file .env -f docker/compose.dev.yml logs -f model-wav2lip

docker-wav2lip-smoke: ## Phase 12Y — probe /health on Wav2Lip wrapper.
	@curl -fsS $${WAV2LIP_BASE_URL:-http://localhost:8068}/health | python3 -m json.tool

docker-musetalk-build: ## Phase 12Y — build the MuseTalk wrapper image (~12 GB).
	@docker compose --env-file .env -f docker/compose.dev.yml --profile musetalk build model-musetalk

docker-musetalk-up: ## Phase 12Y — start MuseTalk wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile musetalk up -d model-musetalk

docker-musetalk-down: ## Phase 12Y — stop MuseTalk wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile musetalk stop model-musetalk

docker-musetalk-logs: ## Phase 12Y — tail MuseTalk wrapper logs.
	@docker compose --env-file .env -f docker/compose.dev.yml logs -f model-musetalk

docker-musetalk-smoke: ## Phase 12Y — probe /health on MuseTalk wrapper.
	@curl -fsS $${MUSETALK_BASE_URL:-http://localhost:8069}/health | python3 -m json.tool

docker-liveportrait-build: ## Phase 12Y — build the LivePortrait wrapper image (~12 GB).
	@docker compose --env-file .env -f docker/compose.dev.yml --profile liveportrait build model-liveportrait

docker-liveportrait-up: ## Phase 12Y — start LivePortrait wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile liveportrait up -d model-liveportrait

docker-liveportrait-down: ## Phase 12Y — stop LivePortrait wrapper.
	@docker compose --env-file .env -f docker/compose.dev.yml --profile liveportrait stop model-liveportrait

docker-liveportrait-logs: ## Phase 12Y — tail LivePortrait wrapper logs.
	@docker compose --env-file .env -f docker/compose.dev.yml logs -f model-liveportrait

docker-liveportrait-smoke: ## Phase 12Y — probe /health on LivePortrait wrapper.
	@curl -fsS $${LIVEPORTRAIT_BASE_URL:-http://localhost:8070}/health | python3 -m json.tool

# ----- Phase 12V — 7 more video generators (operator-opt-in build) -----------
# Pattern: docker-<name>-build / -up / -down / -logs / -smoke
# SVD (img→vid), AnimateDiff (txt→vid via SDXL), LTX (real-time),
# EchoMimic-V2 (lipsync+gestures), Hallo2 (HD lipsync),
# HunyuanVideo (60GB SOTA, 4-bit), Mochi-1 (60GB Genmo, 4-bit).
define _mk_wrapper_targets
docker-$(1)-build:
	@docker compose --env-file .env -f docker/compose.dev.yml --profile $(1) build model-$(1)
docker-$(1)-up:
	@docker compose --env-file .env -f docker/compose.dev.yml --profile $(1) up -d model-$(1)
docker-$(1)-down:
	@docker compose --env-file .env -f docker/compose.dev.yml --profile $(1) stop model-$(1)
docker-$(1)-logs:
	@docker compose --env-file .env -f docker/compose.dev.yml logs -f model-$(1)
docker-$(1)-smoke:
	@curl -fsS http://localhost:$(2)/health | python3 -m json.tool
endef

$(eval $(call _mk_wrapper_targets,svd,8071))
$(eval $(call _mk_wrapper_targets,animatediff,8072))
$(eval $(call _mk_wrapper_targets,ltx,8073))
$(eval $(call _mk_wrapper_targets,echomimic,8074))
$(eval $(call _mk_wrapper_targets,hallo,8075))
$(eval $(call _mk_wrapper_targets,hunyuanvideo,8076))
$(eval $(call _mk_wrapper_targets,mochi,8077))

docker-gpu-config-check: ## Validate compose.dev + compose.gpu overlay (no services started)
	@test -f .env || (echo "ERROR: .env missing. Run: cp .env.example .env" && exit 1)
	@echo ">> compose.dev + compose.gpu overlay config"
	$(COMPOSE_GPU) config >/dev/null
	@echo "OK: GPU overlay merges cleanly with the dev compose."

docker-gpu-build: ## Build ONLY the GPU agent image (Dockerfile.cuda). Default: no torch (INSTALL_TORCH=false). Pass INSTALL_TORCH=true for the Phase 7D-capable image.
	@test -f .env || (echo "ERROR: .env missing. Run: cp .env.example .env" && exit 1)
	@if ! command -v docker >/dev/null 2>&1; then \
		echo "docker not on PATH; cannot build GPU image. Skip."; exit 0; \
	fi
	@echo ">> Building aivideo-agent-cuda (INSTALL_TORCH=$${INSTALL_TORCH:-false})"
	@docker build \
		--build-arg INSTALL_TORCH=$${INSTALL_TORCH:-false} \
		--build-arg INSTALL_SADTALKER_DEPS=$${INSTALL_SADTALKER_DEPS:-false} \
		-f docker/agents/Dockerfile.cuda \
		-t aivideo-agent-cuda:latest \
		.
	@echo "OK: aivideo-agent-cuda built. Run: docker run --rm --gpus all aivideo-agent-cuda:latest"

docker-gpu-down: ## Stop & remove the GPU-profiled services. Light stack stays up.
	@if ! command -v docker >/dev/null 2>&1; then \
		echo "docker not on PATH. Skip."; exit 0; \
	fi
	@echo ">> Stopping GPU-profiled services (agent-voice / agent-face / agent-lipsync)"
	@$(COMPOSE_GPU) --profile gpu stop agent-voice agent-face agent-lipsync 2>&1 || true
	@$(COMPOSE_GPU) --profile gpu rm -f agent-voice agent-face agent-lipsync 2>&1 || true
	@echo "OK: GPU services stopped. Light stack still running (use 'make docker-light-down' for the rest)."

docker-gpu-smoke: ## Run nvidia-smi inside a CUDA container. Skips cleanly when host lacks driver / NVIDIA Container Toolkit.
	@if ! command -v docker >/dev/null 2>&1; then \
		echo "docker not on PATH; cannot smoke-test GPU. Skip."; exit 0; \
	fi
	@if ! docker info 2>/dev/null | grep -qiE "Runtimes:.*nvidia"; then \
		echo ">> NVIDIA Container Toolkit not registered in docker. Skip."; \
		echo "   See docs/runbooks/gpu-runtime.md for setup."; \
		exit 0; \
	fi
	@if ! command -v nvidia-smi >/dev/null 2>&1; then \
		echo ">> nvidia-smi not on host; install the NVIDIA driver first. Skip."; \
		exit 0; \
	fi
	@echo ">> nvidia-smi on host:"
	@nvidia-smi -L 2>&1 || echo "   (no devices found — host has driver but no GPU bound)"
	@echo
	@echo ">> nvidia-smi inside CUDA container (no model download, ~3GB image pull first time):"
	@docker run --rm --gpus all nvidia/cuda:12.4.1-runtime-ubuntu22.04 nvidia-smi 2>&1 \
		|| echo "   (container couldn't see a GPU; check NVIDIA Container Toolkit setup)"

runtime-readiness-check: ## Curl every readiness surface against a running backend. Pair with docker-light-up.
	@curl -fsS http://localhost:$${BACKEND_PORT:-8000}/healthz && echo
	@curl -fsS http://localhost:$${BACKEND_PORT:-8000}/api/v1/system/status && echo
	@curl -fsS http://localhost:$${BACKEND_PORT:-8000}/api/v1/providers | head -c 400; echo
	@curl -fsS http://localhost:$${BACKEND_PORT:-8000}/api/v1/providers/tts | head -c 400; echo
	@curl -fsS http://localhost:$${BACKEND_PORT:-8000}/api/v1/providers/llm | head -c 400; echo
	@echo ">> TTS generate (expect 503 in light)"
	@curl -sS -X POST http://localhost:$${BACKEND_PORT:-8000}/api/v1/tts/generate \
		-H "Content-Type: application/json" \
		-d '{"script_text":"hello","tts_provider_id":"piper"}' -w "\nHTTP %{http_code}\n"
	@echo ">> Script generate (template — always works)"
	@curl -sS -X POST http://localhost:$${BACKEND_PORT:-8000}/api/v1/script/generate \
		-H "Content-Type: application/json" \
		-d '{"brief":"test","target_duration_seconds":30,"provider_id":"template"}' -w "\nHTTP %{http_code}\n"

# ---------------------------------------------------------------------------
# Phase 6B database migration workflow.
#
# Migrations are NOT auto-run by the FastAPI app on startup. The operator
# invokes them explicitly per deploy. ``DATABASE_URL`` is honoured by
# alembic/env.py through app.core.config.settings.
# ---------------------------------------------------------------------------

ALEMBIC := cd backend && alembic

db-migrate: ## Create a new auto-generated migration. Usage: make db-migrate MSG="add ..."
	@if [ -z "$(MSG)" ]; then \
		echo "ERROR: pass MSG=\"…\" describing the change."; exit 1; \
	fi
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

db-upgrade: ## Apply migrations up to head. Use DATABASE_URL or .env to point at the target.
	$(ALEMBIC) upgrade head

db-downgrade: ## Revert one migration. Pass STEP=-N to revert further (e.g. STEP=-2).
	$(ALEMBIC) downgrade $(or $(STEP),-1)

db-current: ## Show the database's current revision
	$(ALEMBIC) current

db-history: ## Show migration history
	$(ALEMBIC) history --verbose

test-integration: ## Alias for `pytest tests/integration`
	pytest -v tests/integration

# ---------------------------------------------------------------------------
# Frontend (Phase 4B). Assumes Node >= 18 + npm. The first run downloads
# Next.js + React; everything after is offline.
# ---------------------------------------------------------------------------

frontend-install: ## Install frontend dependencies (npm ci if lockfile exists, else npm install)
	cd frontend && (test -f package-lock.json && npm ci --no-audit --no-fund || npm install --no-audit --no-fund)

frontend-lint: ## Run `next lint --max-warnings 0`
	cd frontend && npm run lint

frontend-build: ## Run `next build` (production build)
	cd frontend && npm run build

frontend-check: ## Run frontend lint + build (used by phase4b-test)
	cd frontend && npm run lint && npm run build

# ---------------------------------------------------------------------------
# Docker light runtime (Phase 4C). Boots only the metadata-only stack —
# backend, orchestrator (idle), frontend, postgres, redis. NO GPU services,
# NO model containers, NO model weight downloads.
# ---------------------------------------------------------------------------

COMPOSE_LIGHT := docker compose -f docker/compose.dev.yml
COMPOSE_PROD  := docker compose -f docker/compose.prod.yml
COMPOSE_DEV_GPU := docker compose -f docker/compose.dev.yml -f docker/compose.gpu.yml
DOCKER_LIGHT_SERVICES := backend orchestrator frontend postgres redis

docker-config-check: ## Validate dev, prod, and dev+gpu compose configs (no containers started)
	@echo ">> dev compose config"
	$(COMPOSE_LIGHT) config >/dev/null
	@echo ">> prod compose config"
	$(COMPOSE_PROD) config >/dev/null
	@echo ">> dev + gpu overlay config"
	$(COMPOSE_DEV_GPU) config >/dev/null
	@echo "OK: all compose configs valid."

docker-light-build: ## Build only the light-runtime images (backend, orchestrator, frontend). No GPU images.
	@test -f .env || (echo "ERROR: .env missing. Run: cp .env.example .env" && exit 1)
	$(COMPOSE_LIGHT) build backend orchestrator frontend

docker-light-up: ## Start the light stack (postgres, redis, backend, frontend, orchestrator) in the background
	@test -f .env || (echo "ERROR: .env missing. Run: cp .env.example .env" && exit 1)
	$(COMPOSE_LIGHT) up -d $(DOCKER_LIGHT_SERVICES)
	@echo "Light stack starting. Tail logs with: make docker-light-logs"

docker-light-down: ## Stop the light stack
	$(COMPOSE_LIGHT) down

docker-light-reset: ## Stop the light stack AND drop all named volumes (postgres/redis/inputs/artifacts). Use when a schema change adds a column the existing DB doesn't have.
	@echo ">> WARNING: this drops local postgres + redis + inputs + artifacts volumes."
	$(COMPOSE_LIGHT) down -v

docker-light-logs: ## Tail logs from the light stack
	$(COMPOSE_LIGHT) logs -f --tail=200 $(DOCKER_LIGHT_SERVICES)

docker-light-smoke: ## Smoke-test the light stack (backend + frontend HTTP endpoints)
	@echo ">> /healthz"
	@curl -fsS http://localhost:8000/healthz && echo ""
	@echo ">> /api/v1/system/status"
	@curl -fsS http://localhost:8000/api/v1/system/status && echo ""
	@echo ">> /api/v1/jobs"
	@curl -fsS http://localhost:8000/api/v1/jobs && echo ""
	@echo ">> /api/v1/stages"
	@curl -fsS http://localhost:8000/api/v1/stages && echo ""
	@echo ">> frontend /"
	@curl -fsS -o /dev/null -w "frontend HTTP %{http_code}\n" http://localhost:3000/

docker-light-check: ## End-to-end light validation: config -> build -> up -> smoke -> down
	$(MAKE) docker-config-check
	$(MAKE) docker-light-build
	$(MAKE) docker-light-up
	@echo "Waiting up to 45s for backend healthcheck to pass..."
	@for i in $$(seq 1 45); do \
		if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then \
			echo "backend ready after $${i}s"; break; \
		fi; \
		sleep 1; \
	done
	@echo "Waiting up to 60s for frontend to respond..."
	@for i in $$(seq 1 60); do \
		if curl -fsS -o /dev/null http://localhost:3000/ 2>/dev/null; then \
			echo "frontend ready after $${i}s"; break; \
		fi; \
		sleep 1; \
	done
	$(MAKE) docker-light-smoke
	$(MAKE) docker-light-down

# ---------------------------------------------------------------------------
# Lint / format. Both are non-destructive without --fix.
# ---------------------------------------------------------------------------

lint: ## Run ruff (check only)
	ruff check .
	ruff format --check .

fmt: ## Format with ruff
	ruff format .
	ruff check --fix .

# ---------------------------------------------------------------------------
# Misc. None of these run heavy installs or downloads.
# ---------------------------------------------------------------------------

check-env: ## Verify .env exists
	@test -f .env || (echo "Missing .env — copy from .env.example" && exit 1)
	@echo "OK: .env present."

models-check: ## Reminder; real check lands when providers ship in Phase 3
	@echo "Phase 1 does not load any model weights. Phase 3 will add a real check"
	@echo "via each provider's required_assets() under agents/lipsync/providers/*."

# ---------------------------------------------------------------------------
# Phase 11G — Ollama operator helpers.
# Safe by default: nothing here pulls a model or starts the daemon.
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL ?= http://localhost:11434

.PHONY: ollama-status ollama-models ollama-smoke

ollama-status: ## Check whether the Ollama daemon is reachable (no pull).
	@echo "Probing $(OLLAMA_BASE_URL)/api/tags ..."
	@curl -fsS --connect-timeout 3 "$(OLLAMA_BASE_URL)/api/tags" >/dev/null \
		&& echo "OK: Ollama daemon reachable at $(OLLAMA_BASE_URL)" \
		|| (echo "FAIL: Ollama daemon NOT reachable at $(OLLAMA_BASE_URL)"; \
		    echo "  install / start Ollama and re-run; see docs/runbooks/ollama-scriptwriter.md"; \
		    exit 1)

ollama-models: ## List models pulled on the reachable Ollama daemon (no pull).
	@curl -fsS --connect-timeout 3 "$(OLLAMA_BASE_URL)/api/tags" \
		| python3 -c "import json,sys; d=json.load(sys.stdin); \
			print('Models on '+'$(OLLAMA_BASE_URL)'+':'); \
			[print(f'  {m[\"name\"]:<30} size={m.get(\"size\",0)//1024//1024} MB') for m in d.get('models',[])]" \
		|| (echo "FAIL: could not read /api/tags from $(OLLAMA_BASE_URL)"; exit 1)

ollama-smoke: ## Local smoke against the configured model; FAILS if model not pulled (operator must pull manually).
	@MODEL=$${OLLAMA_MODEL:-qwen3.6}; \
		echo "Smoke: $(OLLAMA_BASE_URL) model=$$MODEL"; \
		curl -fsS --connect-timeout 3 --max-time 60 \
			-H 'Content-Type: application/json' \
			-d "$$(printf '{\"model\":\"%s\",\"prompt\":\"Salut, scrie un cuvant in romana\",\"stream\":false}' $$MODEL)" \
			"$(OLLAMA_BASE_URL)/api/generate" \
			| python3 -c "import json,sys; d=json.load(sys.stdin); \
				print('OK: model responded — first 80 chars: '+(d.get('response','') or '')[:80])" \
		|| (echo "FAIL: smoke against $$MODEL failed — confirm 'ollama pull $$MODEL' has run on $(OLLAMA_BASE_URL)"; exit 1)

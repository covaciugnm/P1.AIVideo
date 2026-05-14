# P1.AIVideo Makefile.
# Targets are safe by default — they do not auto-build images, install deps,
# or download model weights. Phase-1+ commands assume you have already run
# the install step described in docs/runbooks/dev-setup.md.

COMPOSE_DEV  := docker compose -f docker/compose.dev.yml
COMPOSE_GPU  := docker compose -f docker/compose.dev.yml -f docker/compose.gpu.yml

.PHONY: help up up-gpu down logs ps test test-unit test-integration lint fmt \
        check-env models-check phase1-test phase2-test phase3a-test phase3b-test phase3c-test phase3d-test phase3e-test phase3f-test phase3g-test phase3h-test phase3i-test phase3j-test phase4a-test phase4a2-test phase4b-test phase4d-test phase4e-test phase4f-test phase4f2-test phase4f3-test \
        frontend-install frontend-lint frontend-build frontend-check \
        docker-config-check docker-light-build docker-light-up docker-light-down docker-light-logs docker-light-smoke docker-light-check

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

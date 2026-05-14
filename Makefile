# P1.AIVideo Makefile.
# Targets are safe by default — they do not auto-build images, install deps,
# or download model weights. Phase-1+ commands assume you have already run
# the install step described in docs/runbooks/dev-setup.md.

COMPOSE_DEV  := docker compose -f docker/compose.dev.yml
COMPOSE_GPU  := docker compose -f docker/compose.dev.yml -f docker/compose.gpu.yml

.PHONY: help up up-gpu down logs ps test test-unit test-integration lint fmt \
        check-env models-check phase1-test phase2-test phase3a-test phase3b-test phase3c-test phase3d-test phase3e-test phase3f-test phase3g-test phase3h-test phase3i-test phase3j-test phase4a-test phase4a2-test phase4b-test \
        frontend-install frontend-lint frontend-build frontend-check

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

# P1.AIVideo Makefile.
# Targets are safe by default — they do not auto-build images, install deps,
# or download model weights. Phase-1+ commands assume you have already run
# the install step described in docs/runbooks/dev-setup.md.

COMPOSE_DEV  := docker compose -f docker/compose.dev.yml
COMPOSE_GPU  := docker compose -f docker/compose.dev.yml -f docker/compose.gpu.yml

.PHONY: help up up-gpu down logs ps test test-unit test-integration lint fmt \
        check-env models-check phase1-test phase2-test phase3a-test phase3b-test

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

test-integration: ## Alias for `pytest tests/integration`
	pytest -v tests/integration

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

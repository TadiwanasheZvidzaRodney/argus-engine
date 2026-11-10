.PHONY: help dev dev-up dev-down test test-py test-ts lint lint-py lint-ts typecheck format format-check migrate seed clean contracts check

SHELL := /bin/bash
PYTHON := uv run
PNPM := pnpm

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Local stack lifecycle ---

dev-up: ## Start local database, cache, and LocalStack containers
	docker compose up -d postgres neo4j redis localstack mailpit
	@echo "Waiting for services to become healthy..."
	@timeout 60 bash -c 'until docker compose ps | grep -E "postgres.*healthy" >/dev/null; do sleep 1; done'
	@echo "PostgreSQL is ready."

dev-down: ## Stop all local containers and preserve volumes
	docker compose down

dev-clean: ## Stop all local containers and erase volumes
	docker compose down -v --remove-orphans

dev: dev-up migrate seed ## Bring up dependencies, migrate, seed, and show service commands
	@echo ""
	@echo "Argus Engine local development stack is ready:"
	@echo "  - PostgreSQL: localhost:5432 (db: argus, user: argus)"
	@echo "  - Neo4j:      http://localhost:7474 (bolt://localhost:7687, user: neo4j)"
	@echo "  - Redis:      localhost:6379"
	@echo "  - LocalStack: http://localhost:4566"
	@echo "  - Mailpit:    http://localhost:8025"
	@echo ""
	@echo "Run services in separate terminals:"
	@echo "  API:     $(PYTHON) uvicorn argus_api.main:app_factory --factory --reload --port 8000"
	@echo "  WS:      $(PYTHON) uvicorn argus_ws.main:app_factory --factory --reload --port 8001"
	@echo "  Worker:  $(PYTHON) -m argus_worker.main run --interval 10"
	@echo "  Web:     $(PNPM) --filter @argus/web dev"

# --- Database & Seeds ---

migrate: ## Run Alembic migrations up to head
	cd services/api && $(PYTHON) alembic upgrade head

seed: ## Seed demo tenant and test data in local Postgres and Neo4j
	$(PYTHON) -m scripts.seed

# --- Testing ---

test: test-py test-ts ## Run all test suites

test-py: ## Run Python test suites with pytest
	$(PYTHON) pytest

test-ts: ## Run TypeScript test suites with Vitest
	$(PNPM) turbo run test

test-e2e: ## Run Playwright end-to-end browser tests
	$(PNPM) --filter @argus/web e2e

# --- Linting & Formatting ---

lint: lint-py lint-ts ## Run all linters

lint-py: ## Lint Python with Ruff
	$(PYTHON) ruff check .

lint-ts: ## Lint TypeScript with ESLint
	$(PNPM) turbo run lint

typecheck: ## Typecheck all Python and TypeScript
	$(PYTHON) mypy
	$(PNPM) turbo run typecheck

format: ## Format all Python and TypeScript files
	$(PYTHON) ruff format .
	$(PYTHON) ruff check --fix .
	$(PNPM) format

format-check: ## Check formatting without editing
	$(PYTHON) ruff format --check .
	$(PNPM) format:check

# --- Contracts ---

contracts: ## Re-export JSON Schemas from Python contract models
	$(PYTHON) -m argus_core.schema_export export packages/contracts/schemas

contracts-check: ## Verify checked-in JSON Schemas match Python models
	$(PYTHON) -m argus_core.schema_export check packages/contracts/schemas

# --- Monorepo Build ---

build: ## Build all deployable packages and apps
	$(PNPM) turbo run build

# --- CI Pipeline Run (local check) ---

check: contracts-check format-check lint typecheck test ## Run full local verification gate
	@echo "All verification checks passed successfully!"

clean: ## Clean build artifacts, caches, and test results
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml dist build
	rm -rf apps/web/.next apps/web/out apps/web/test-results apps/web/.playwright
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "node_modules" -prune -o -name ".turbo" -exec rm -rf {} +

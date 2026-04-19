.DEFAULT_GOAL := help
SHELL := /bin/bash

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: ## First-time setup (install, env, services, migrate, seed)
	./scripts/setup.sh

services: ## Start backing Docker services (postgres, redis, minio, chromadb)
	docker compose up -d postgres redis minio chromadb

api: services ## Run FastAPI on :8080 (foreground; one terminal)
	cd backend && uv run uvicorn app.main:app --reload --port 8080

worker: services ## Run Celery worker (foreground; one terminal)
	cd backend && uv run celery -A app.worker.celery_app worker --loglevel=info --concurrency=1

beat: services ## Run Celery beat scheduler (foreground; one terminal)
	cd backend && uv run celery -A app.worker.celery_app beat --loglevel=info

web: ## Run Vite dev server on :5173 (foreground; one terminal)
	cd frontend && npm run dev

tilt: ## Start full dev stack via Tilt (infra + api + workers + web)
	@command -v tilt >/dev/null || { echo "tilt not installed. Install: https://docs.tilt.dev/install.html"; exit 1; }
	tilt up

tilt-down: ## Stop the Tilt dev stack
	tilt down

lint: ## Lint + format everything
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd frontend && npm run lint && npm run format

migrate: ## Run database migrations
	cd backend && uv run alembic upgrade head

generate: ## Regenerate frontend API client
	cd frontend && npm run generate-api

# Env-var overrides baked in at the Make layer so pytest never touches
# the dev database even if a conftest `pytest_configure` hook misfires.
# The `_test` DB name is the last-line-of-defence check inside the
# fixtures themselves.
TEST_ENV = DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/hr_screening_test \
           REDIS_URL=redis://localhost:6379/15 \
           DEBUG=false \
           ENCRYPTION_KEYS=bwKiCtnOedgvw_E3RtRehIznu_GR2i_8sAPM2oBRYv0=

test: services ## Run backend tests (real postgres + redis; mocked Google HTTP)
	cd backend && $(TEST_ENV) uv run pytest tests -xvs --ignore=tests/eval

eval: services ## Run search quality eval (slower; hits real ChromaDB)
	cd backend && $(TEST_ENV) uv run pytest tests/eval -xvs

eval-intent: services ## Run F81.g intent-classification accuracy eval
	cd backend && $(TEST_ENV) uv run pytest tests/eval/test_intent_accuracy.py -xvs

eval-parser: ## Run F89.a query-parser accuracy eval
	cd backend && $(TEST_ENV) uv run pytest tests/eval/test_query_parser_accuracy.py -xvs

stop: ## Stop Docker services
	docker compose down

prod-up: ## Build + start production stack
	docker compose -f docker-compose.prod.yml up -d --build

prod-down: ## Stop production stack
	docker compose -f docker-compose.prod.yml down

prod-logs: ## Tail production logs
	docker compose -f docker-compose.prod.yml logs -f --tail=50

clean: stop ## Stop services + remove caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.ruff_cache frontend/dist

.PHONY: help setup services api worker beat web tilt tilt-down lint migrate generate test eval eval-intent eval-parser stop prod-up prod-down prod-logs clean

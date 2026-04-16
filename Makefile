.DEFAULT_GOAL := help
SHELL := /bin/bash

# ── Colors ──────────────────────────────────────────────
CYAN  := \033[36m
GREEN := \033[32m
RESET := \033[0m

# ── Config ──────────────────────────────────────────────
BACKEND  := backend
FRONTEND := frontend

.PHONY: help
help: ## Show this help
	@printf "$(GREEN)Hireflow$(RESET) — AI-Powered HR Screening System\n\n"
	@printf "Usage: make $(CYAN)<target>$(RESET)\n\n"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ { printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ── Infrastructure ──────────────────────────────────────
.PHONY: services services-down services-logs

services: ## Start all Docker services (postgres, redis, minio, chromadb)
	docker compose up -d postgres redis minio chromadb
	@docker compose up minio-setup 2>/dev/null || true

services-down: ## Stop all Docker services
	docker compose down

services-logs: ## Tail Docker service logs
	docker compose logs -f --tail=50

# ── Backend ─────────────────────────────────────────────
.PHONY: backend-install backend-dev backend-worker backend-lint backend-migrate backend-seed

backend-install: ## Install backend dependencies
	cd $(BACKEND) && uv sync --extra dev

backend-dev: ## Start FastAPI dev server (port 8000)
	cd $(BACKEND) && uv run uvicorn app.main:app --reload

backend-worker: ## Start Celery worker
	cd $(BACKEND) && uv run celery -A app.worker.celery_app worker --loglevel=info

backend-lint: ## Lint + format backend (ruff)
	cd $(BACKEND) && uv run ruff check --fix . && uv run ruff format .

backend-migrate: ## Run Alembic migrations to head
	cd $(BACKEND) && uv run alembic upgrade head

backend-migration: ## Generate a new Alembic migration (usage: make backend-migration msg="add foo table")
	cd $(BACKEND) && uv run alembic revision --autogenerate -m "$(msg)"

backend-seed: ## Create/promote admin user (set ADMIN_EMAIL + ADMIN_PASSWORD)
	cd $(BACKEND) && uv run python scripts/create_admin.py

backend-test: ## Run backend tests
	cd $(BACKEND) && uv run pytest

# ── Frontend ────────────────────────────────────────────
.PHONY: frontend-install frontend-dev frontend-lint frontend-build frontend-generate

frontend-install: ## Install frontend dependencies
	cd $(FRONTEND) && npm install

frontend-dev: ## Start Vite dev server (port 5173)
	cd $(FRONTEND) && npm run dev

frontend-lint: ## Lint + format frontend (eslint + prettier)
	cd $(FRONTEND) && npm run lint && npm run format

frontend-build: ## Production build
	cd $(FRONTEND) && npm run build

frontend-generate: ## Regenerate TypeScript API client from OpenAPI spec
	cd $(FRONTEND) && npm run generate-api

# ── Compound ────────────────────────────────────────────
.PHONY: install dev lint generate clean reset

install: backend-install frontend-install ## Install all dependencies

dev: ## Start everything for local development (services + backend + worker + frontend)
	@echo "Starting services..."
	@$(MAKE) services
	@echo ""
	@echo "Run these in separate terminals:"
	@echo "  $(CYAN)make backend-dev$(RESET)     — FastAPI on :8000"
	@echo "  $(CYAN)make backend-worker$(RESET)  — Celery worker"
	@echo "  $(CYAN)make frontend-dev$(RESET)    — Vite on :5173"

lint: backend-lint frontend-lint ## Lint + format everything

generate: frontend-generate ## Regenerate API client

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND)/.ruff_cache $(FRONTEND)/dist

reset: services-down clean ## Stop services + clean caches
	@echo "$(GREEN)Reset complete.$(RESET) Run 'make install && make dev' to start fresh."

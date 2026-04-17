.DEFAULT_GOAL := help
SHELL := /bin/bash

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: ## First-time setup (install, env, services, migrate, seed)
	cd backend && uv sync --extra dev
	cd frontend && npm install --silent
	@test -f backend/.env || (cp backend/.env.example backend/.env && \
		sed -i "s/^JWT_SECRET_KEY=$$/JWT_SECRET_KEY=$$(openssl rand -hex 32)/" backend/.env && \
		echo "Created backend/.env")
	@grep -q '^ENCRYPTION_KEYS=.\+' backend/.env || (cd backend && \
		KEY=$$(uv run python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())") && \
		sed -i "s|^ENCRYPTION_KEYS=.*|ENCRYPTION_KEYS=$$KEY|" .env && \
		(grep -q '^ENCRYPTION_KEYS=' .env || echo "ENCRYPTION_KEYS=$$KEY" >> .env) && \
		echo "Generated ENCRYPTION_KEYS in backend/.env")
	@test -f frontend/.env || (cp frontend/.env.example frontend/.env && echo "Created frontend/.env")
	docker compose up -d postgres redis minio chromadb
	@docker compose up minio-setup 2>/dev/null || true
	@echo "Waiting for services..." && sleep 3
	cd backend && uv run alembic upgrade head
	cd backend && ADMIN_EMAIL=admin@hireflow.io ADMIN_PASSWORD=admin123 uv run python scripts/create_admin.py
	@echo ""
	@echo "Ready. Open four terminals and run:"
	@echo "  make api        # FastAPI    :8080"
	@echo "  make worker     # Celery worker"
	@echo "  make beat       # Celery beat (periodic tasks)"
	@echo "  make web        # Vite       :5173"
	@echo ""
	@echo "Admin: admin@hireflow.io / admin123"

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

.PHONY: help setup services api worker beat web lint migrate generate test eval stop prod-up prod-down prod-logs clean

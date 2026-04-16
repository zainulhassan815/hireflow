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
	@test -f frontend/.env || (cp frontend/.env.example frontend/.env && echo "Created frontend/.env")
	docker compose up -d postgres redis minio chromadb
	@docker compose up minio-setup 2>/dev/null || true
	@echo "Waiting for services..." && sleep 3
	cd backend && uv run alembic upgrade head
	cd backend && ADMIN_EMAIL=admin@hireflow.io ADMIN_PASSWORD=admin123 uv run python scripts/create_admin.py
	@echo "\nReady. Run: make dev"
	@echo "Admin: admin@hireflow.io / admin123"

dev: ## Start API + worker + frontend (use Ctrl-C to stop)
	@docker compose up -d postgres redis minio chromadb >/dev/null 2>&1
	@trap 'kill 0' EXIT; \
		cd backend && uv run uvicorn app.main:app --reload --port 8080 & \
		cd backend && uv run celery -A app.worker.celery_app worker --loglevel=warning --concurrency=1 & \
		cd frontend && npm run dev & \
		wait

lint: ## Lint + format everything
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd frontend && npm run lint && npm run format

migrate: ## Run database migrations
	cd backend && uv run alembic upgrade head

generate: ## Regenerate frontend API client
	cd frontend && npm run generate-api

stop: ## Stop Docker services
	docker compose down

clean: stop ## Stop services + remove caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.ruff_cache frontend/dist

.PHONY: help setup dev lint migrate generate stop clean

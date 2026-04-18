#!/usr/bin/env bash
# First-time setup for the Hireflow dev environment.
# Installs deps, seeds env files, starts infra, runs migrations, creates admin.
# Run from repo root: ./scripts/setup.sh  (or `make setup`).

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Installing backend deps"
(cd backend && uv sync --extra dev)

echo "==> Installing frontend deps"
(cd frontend && npm install --silent)

echo "==> Seeding backend/.env"
if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    sed -i "s/^JWT_SECRET_KEY=$/JWT_SECRET_KEY=$(openssl rand -hex 32)/" backend/.env
    echo "    Created backend/.env"
fi

if ! grep -q '^ENCRYPTION_KEYS=.\+' backend/.env; then
    KEY=$(cd backend && uv run python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
    if grep -q '^ENCRYPTION_KEYS=' backend/.env; then
        sed -i "s|^ENCRYPTION_KEYS=.*|ENCRYPTION_KEYS=$KEY|" backend/.env
    else
        echo "ENCRYPTION_KEYS=$KEY" >> backend/.env
    fi
    echo "    Generated ENCRYPTION_KEYS in backend/.env"
fi

echo "==> Seeding frontend/.env"
if [ ! -f frontend/.env ]; then
    cp frontend/.env.example frontend/.env
    echo "    Created frontend/.env"
fi

echo "==> Starting infra services"
docker compose up -d postgres redis minio chromadb

echo "==> Bootstrapping minio bucket"
docker compose --profile setup run --rm minio-setup 2>/dev/null || true

echo "==> Waiting for services"
sleep 3

echo "==> Running migrations"
(cd backend && uv run alembic upgrade head)

echo "==> Creating admin user"
(cd backend && ADMIN_EMAIL=admin@hireflow.io ADMIN_PASSWORD=admin123 uv run python scripts/create_admin.py)

cat <<'EOF'

Ready. Recommended:
  make tilt       # one command for infra + api + workers + web (UI :10350)

Or run each in its own terminal:
  make api        # FastAPI    :8080
  make worker     # Celery worker
  make beat       # Celery beat (periodic tasks)
  make web        # Vite       :5173

Admin: admin@hireflow.io / admin123
EOF

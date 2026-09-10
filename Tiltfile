# Hireflow dev orchestrator. Run `tilt up` from the repo root.
# UI: http://localhost:10350

docker_compose('./docker-compose.yml')

# Group infra services in the UI.
for svc in ['postgres', 'redis', 'chromadb', 'minio']:
    dc_resource(svc, labels=['infra'])

# One-shot bucket bootstrap. Runs against the compose `minio-setup` service
# (gated behind the "setup" profile so it doesn't auto-start as a long-running
# container, which Tilt would mistake for a failed daemon).
local_resource(
    'minio-bucket',
    cmd='docker compose --profile setup run --rm minio-setup',
    resource_deps=['minio'],
    labels=['infra'],
)

local_resource(
    'backend',
    serve_cmd='uv run uvicorn app.main:app --reload --port 8090',
    serve_dir='backend',
    # HF_HUB_DISABLE_XET: HuggingFace's xet transfer backend stalls
    # indefinitely on some networks — a 0-byte .incomplete blob and no
    # progress, which reads as a hung app. Plain HTTP is slower but finishes.
    serve_env={'PYTHONUNBUFFERED': '1', 'HF_HUB_DISABLE_XET': '1'},
    resource_deps=['postgres', 'redis', 'chromadb', 'minio-setup'],
    readiness_probe=probe(
        http_get=http_get_action(port=8090, path='/api/health'),
        period_secs=2,
    ),
    links=[link('http://localhost:8090/docs', 'Swagger')],
    labels=['app'],
)

local_resource(
    'celery-worker',
    serve_cmd='uv run celery -A app.worker.celery_app worker --loglevel=info --concurrency=1',
    serve_dir='backend',
    serve_env={'HF_HUB_DISABLE_XET': '1'},
    # `deps` is what makes Tilt watch files and restart the resource.
    # Without it a serve_cmd starts once and runs stale code forever.
    # The backend and frontend get away with omitting it only because
    # uvicorn --reload and Vite watch for themselves; Celery has no
    # equivalent, so these two need Tilt to do it.
    deps=['backend/app'],
    resource_deps=['postgres', 'redis'],
    labels=['app'],
)

local_resource(
    'celery-beat',
    serve_cmd='uv run celery -A app.worker.celery_app beat --loglevel=info',
    serve_dir='backend',
    # Beat only reads the schedule at startup, so a changed interval or a
    # new periodic task needs the same restart-on-change as the worker.
    deps=['backend/app/worker'],
    resource_deps=['redis'],
    labels=['app'],
)

local_resource(
    'frontend',
    serve_cmd='npm run dev',
    serve_dir='frontend',
    resource_deps=['backend'],
    links=[link('http://localhost:5173', 'App')],
    labels=['app'],
)

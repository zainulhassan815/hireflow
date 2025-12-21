#!/bin/bash
set -e

BACKEND_URL="${BACKEND_URL:-http://localhost:8001}"

echo "Fetching OpenAPI spec from $BACKEND_URL..."
curl -s "$BACKEND_URL/openapi.json" -o frontend/openapi.json

echo "Preprocessing OpenAPI spec..."
node scripts/preprocess-openapi.js

echo "Generating API client..."
cd frontend && npx @hey-api/openapi-ts

echo "Done!"

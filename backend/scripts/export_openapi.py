"""Dump the FastAPI OpenAPI spec to a file for frontend codegen.

Writes to frontend/openapi.json by default (path relative to repo root).

Usage:
    uv run python -m scripts.export_openapi [output_path]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# JWT_SECRET_KEY is required by config.py on import. For spec export we only
# need to instantiate the app, so a throwaway secret is fine.
os.environ.setdefault("JWT_SECRET_KEY", "x" * 32)

from app.main import app  # noqa: E402


def main() -> int:
    default_path = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Dump the FastAPI OpenAPI spec to a file for frontend codegen.

Writes to frontend/openapi.json by default (path relative to repo root).

Usage:
    uv run python scripts/export_openapi.py [output_path]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    os.environ.setdefault("JWT_SECRET_KEY", "a]kP9#mQ$2xR!vN7&wZ5^tL0@dF3+hY8")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.main import app

    default_path = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.api_config import custom_generate_unique_id
from app.core.config import settings
from app.api.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="AI-Powered HR Screening and Document Retrieval System Using RAG",
        version="0.1.0",
        generate_unique_id_function=custom_generate_unique_id,
        openapi_tags=[
            {"name": "auth", "description": "Authentication operations"},
            {"name": "jobs", "description": "Job posting management"},
            {"name": "documents", "description": "Resume and document management"},
            {"name": "search", "description": "Semantic search and RAG queries"},
            {"name": "applications", "description": "Job applications management"},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite default
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    return app


app = create_app()

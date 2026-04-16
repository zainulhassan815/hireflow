from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import handle_domain_error
from app.api.router import api_router
from app.core.api_config import custom_generate_unique_id
from app.core.config import settings
from app.domain.exceptions import DomainError


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="AI-Powered HR Screening and Document Retrieval System Using RAG",
        version="0.1.0",
        generate_unique_id_function=custom_generate_unique_id,
        openapi_tags=[
            {
                "name": "auth",
                "description": (
                    "Registration, login, token refresh, logout, and password reset."
                ),
            },
            {
                "name": "users",
                "description": "User administration (admin only).",
            },
            {
                "name": "documents",
                "description": (
                    "Document upload, listing, metadata retrieval, "
                    "download, and deletion."
                ),
            },
            {
                "name": "jobs",
                "description": "Job posting management.",
            },
            {
                "name": "search",
                "description": "Hybrid semantic + metadata search across documents.",
            },
            {
                "name": "rag",
                "description": (
                    "Retrieval-Augmented Generation: ask questions about "
                    "uploaded documents and get AI-generated answers with citations."
                ),
            },
            {
                "name": "candidates",
                "description": "Candidate management and job applications.",
            },
            {
                "name": "logs",
                "description": "Activity audit trail.",
            },
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(DomainError, handle_domain_error)

    app.include_router(api_router, prefix="/api")

    return app


app = create_app()

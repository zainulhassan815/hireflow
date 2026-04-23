import logging

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import (
    handle_domain_error,
    handle_http_exception,
    handle_unexpected,
    handle_validation_error,
)
from app.api.router import api_router
from app.core.api_config import custom_generate_unique_id
from app.core.config import settings
from app.core.encryption import get_cipher
from app.domain.exceptions import DomainError


def _configure_dev_logging() -> None:
    # basicConfig is a no-op when the root logger already has handlers,
    # so uvicorn reload and pytest (which configures its own) are safe.
    if settings.debug:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )


def create_app() -> FastAPI:
    _configure_dev_logging()
    get_cipher()  # fail-fast if ENCRYPTION_KEYS is unset

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
            {
                "name": "gmail",
                "description": (
                    "Gmail OAuth: connect, disconnect, status. Actual resume "
                    "syncing and email sending land in later features."
                ),
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
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected)

    app.include_router(api_router, prefix="/api")

    return app


app = create_app()

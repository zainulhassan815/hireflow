"""RAG question-answering endpoint."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, RagServiceDep
from app.domain.exceptions import ServiceUnavailable
from app.schemas.errors import ErrorResponse
from app.schemas.rag import RagRequest, RagResponse, SourceCitation

router = APIRouter()


@router.post(
    "/query",
    response_model=RagResponse,
    summary="Ask a question about documents",
    description=(
        "Retrieval-Augmented Generation: finds the most relevant document "
        "chunks via vector search, builds a context window, and sends the "
        "question to the configured LLM (Claude or Ollama). Returns the "
        "generated answer with source citations pointing to the exact "
        "chunks used. Requires both ChromaDB and an LLM provider to be "
        "configured."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        503: {
            "model": ErrorResponse,
            "description": "RAG not available (ChromaDB or LLM not configured)",
        },
    },
)
async def query_documents(
    request: RagRequest,
    current_user: CurrentUser,
    rag: RagServiceDep,
) -> RagResponse:
    if rag is None:
        raise ServiceUnavailable(
            "RAG is not available. Configure an LLM provider "
            "(ANTHROPIC_API_KEY or Ollama) and ensure ChromaDB is running."
        )

    result = await rag.query(
        question=request.question,
        document_ids=request.document_ids,
        max_chunks=request.max_chunks,
    )
    return RagResponse(
        answer=result.answer,
        citations=[SourceCitation(**c) for c in result.citations],
        model=result.model,
        query_time_ms=result.query_time_ms,
    )

"""Search endpoints."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SearchServiceDep
from app.schemas.search import SearchRequest, SearchResponse, SearchResultItem

router = APIRouter()


@router.post(
    "",
    response_model=SearchResponse,
    summary="Search documents",
    description=(
        "Hybrid search combining vector similarity (ChromaDB) with structured "
        "metadata filtering (PostgreSQL). Results are merged using Reciprocal "
        "Rank Fusion. Returns matching documents with relevance scores and "
        "text highlights from the most relevant chunks."
    ),
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def search_documents(
    request: SearchRequest,
    current_user: CurrentUser,
    search: SearchServiceDep,
) -> SearchResponse:
    results, query_time_ms = await search.search(
        actor=current_user,
        query=request.query,
        document_type=request.document_type,
        skills=request.skills,
        min_experience_years=request.min_experience_years,
        date_from=request.date_from,
        date_to=request.date_to,
        limit=request.limit,
    )
    return SearchResponse(
        results=[SearchResultItem(**r) for r in results],
        total=len(results),
        query_time_ms=query_time_ms,
    )

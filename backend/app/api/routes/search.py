"""Search endpoints."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SearchServiceDep
from app.schemas.search import SearchRequest, SearchResponse, SearchResultItem
from app.services.query_parser_vocab import KNOWN_SKILLS

router = APIRouter()


@router.get(
    "/skills",
    response_model=list[str],
    summary="List the canonical skill vocabulary",
    description=(
        "Returns the sorted, lowercased ``KNOWN_SKILLS`` set used by "
        "the rule-based classifier and the F89.a query parser. "
        "Frontends use this for skill-picker suggestions on the "
        "search + documents filter bars (F32). The vocabulary is "
        "small (~80 entries) and stable enough that a single GET "
        "on page mount is fine.\n\n"
        "Free-text submission is also accepted by ``GET /documents`` "
        "and ``POST /search`` — a skill not in the canonical vocab "
        "still filters correctly. The endpoint is the suggestion "
        "source, not a contract."
    ),
    responses={
        401: {"description": "Not authenticated"},
    },
)
def list_known_skills(current_user: CurrentUser) -> list[str]:
    # ``current_user`` reads as unused but is the auth gate — every
    # authenticated user gets the same vocabulary.
    del current_user
    return sorted(KNOWN_SKILLS)


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

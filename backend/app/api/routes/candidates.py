"""Candidate and application endpoints."""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CandidateServiceDep, CurrentUser, DocumentServiceDep
from app.models.candidate import ApplicationStatus
from app.schemas.candidate import (
    ApplicationResponse,
    CandidateResponse,
    UpdateApplicationStatusRequest,
)

router = APIRouter()


@router.post(
    "/from-document/{document_id}",
    response_model=CandidateResponse,
    status_code=201,
    summary="Create candidate from document",
    description=(
        "Create a candidate record from a processed resume document. "
        "Extracts name, email, skills, experience from the document's metadata. "
        "Idempotent: returns existing candidate if already created from this document."
    ),
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Document not found"},
    },
)
async def create_candidate_from_document(
    document_id: UUID,
    current_user: CurrentUser,
    candidates: CandidateServiceDep,
    documents: DocumentServiceDep,
) -> CandidateResponse:
    doc = await documents.get(document_id, actor=current_user)
    candidate = await candidates.create_from_document(doc, owner=current_user)
    return CandidateResponse.model_validate(candidate)


@router.get(
    "",
    response_model=list[CandidateResponse],
    summary="List my candidates",
    description="Return candidates owned by the authenticated user.",
    responses={401: {"description": "Not authenticated"}},
)
async def list_candidates(
    current_user: CurrentUser,
    candidates: CandidateServiceDep,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[CandidateResponse]:
    result = await candidates.list_for_user(current_user.id, limit=limit, offset=offset)
    return [CandidateResponse.model_validate(c) for c in result]


@router.get(
    "/{candidate_id}",
    response_model=CandidateResponse,
    summary="Get candidate details",
    description="Return details for a single candidate.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the candidate owner or an admin"},
        404: {"description": "Candidate not found"},
    },
)
async def get_candidate(
    candidate_id: UUID,
    current_user: CurrentUser,
    candidates: CandidateServiceDep,
) -> CandidateResponse:
    candidate = await candidates.get(candidate_id, actor=current_user)
    return CandidateResponse.model_validate(candidate)


@router.post(
    "/{candidate_id}/apply/{job_id}",
    response_model=ApplicationResponse,
    status_code=201,
    summary="Apply candidate to a job",
    description=(
        "Create an application linking a candidate to a job. "
        "Idempotent: returns existing application if already applied."
    ),
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Candidate or job not found"},
    },
)
async def apply_candidate_to_job(
    candidate_id: UUID,
    job_id: UUID,
    current_user: CurrentUser,
    candidates: CandidateServiceDep,
) -> ApplicationResponse:
    app = await candidates.apply_to_job(candidate_id, job_id, actor=current_user)
    return ApplicationResponse.model_validate(app)


@router.get(
    "/jobs/{job_id}/applications",
    response_model=list[ApplicationResponse],
    summary="List applications for a job",
    description=(
        "Return all applications for a job, sorted by match score "
        "descending. Owner-scoped: HR users see only their own jobs' "
        "applications; admins see across owners."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the job owner or an admin"},
        404: {"description": "Job not found"},
    },
)
async def list_job_applications(
    job_id: UUID,
    current_user: CurrentUser,
    candidates: CandidateServiceDep,
    status: ApplicationStatus | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[ApplicationResponse]:
    apps = await candidates.list_applications_for_job(
        job_id, actor=current_user, status=status, limit=limit, offset=offset
    )
    return [ApplicationResponse.model_validate(a) for a in apps]


@router.patch(
    "/applications/{application_id}/status",
    response_model=ApplicationResponse,
    summary="Update application status",
    description=(
        "Shortlist, reject, or advance an application. Owner-scoped by "
        "the parent job: HR users can only change status on applications "
        "for jobs they own; admins bypass."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the parent job's owner or an admin"},
        404: {"description": "Application not found"},
    },
)
async def update_application_status(
    application_id: UUID,
    request: UpdateApplicationStatusRequest,
    current_user: CurrentUser,
    candidates: CandidateServiceDep,
) -> ApplicationResponse:
    app = await candidates.update_application_status(
        application_id, request.status, actor=current_user
    )
    return ApplicationResponse.model_validate(app)

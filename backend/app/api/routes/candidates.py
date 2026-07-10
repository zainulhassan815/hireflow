"""Candidate and application endpoints."""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CandidateServiceDep, CurrentUser, DocumentServiceDep
from app.models.candidate import ApplicationStatus, CandidateAttachment
from app.schemas.candidate import (
    AddAttachmentsRequest,
    ApplicationResponse,
    BulkUpdateApplicationStatusRequest,
    BulkUpdateApplicationStatusResponse,
    CandidateAttachmentResponse,
    CandidateResponse,
    UpdateApplicationStatusRequest,
)

router = APIRouter()


def _attachment_response(
    attachment: CandidateAttachment, document
) -> CandidateAttachmentResponse:
    return CandidateAttachmentResponse(
        document_id=attachment.document_id,
        role=attachment.role,
        filename=document.filename,
        document_type=document.document_type,
        status=document.status,
        created_at=attachment.created_at,
    )


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


@router.get(
    "/{candidate_id}/attachments",
    response_model=list[CandidateAttachmentResponse],
    summary="List candidate attachments",
    description=(
        "Return the files attached to a candidate (resume, certificates, "
        "portfolio, …), each with its role and processing status."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the candidate owner or an admin"},
        404: {"description": "Candidate not found"},
    },
)
async def list_candidate_attachments(
    candidate_id: UUID,
    current_user: CurrentUser,
    candidates: CandidateServiceDep,
) -> list[CandidateAttachmentResponse]:
    attachments = await candidates.list_attachments(candidate_id, actor=current_user)
    return [_attachment_response(a, a.document) for a in attachments]


@router.post(
    "/{candidate_id}/attachments",
    response_model=list[CandidateAttachmentResponse],
    status_code=201,
    summary="Attach documents to a candidate",
    description=(
        "Attach one or more already-uploaded documents to a candidate, "
        "each tagged with a role. Persisted atomically. A candidate may "
        "hold only one resume — attaching a second returns 409. Documents "
        "already attached are skipped. Credential files (certificate / "
        "transcript / portfolio) merge their skills into the candidate "
        "profile."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the candidate/document owner or an admin"},
        404: {"description": "Candidate or a document not found"},
        409: {"description": "Candidate already has a resume attached"},
    },
)
async def add_candidate_attachments(
    candidate_id: UUID,
    request: AddAttachmentsRequest,
    current_user: CurrentUser,
    candidates: CandidateServiceDep,
    documents: DocumentServiceDep,
) -> list[CandidateAttachmentResponse]:
    # Validate each document's existence + ownership before attaching so a
    # cross-tenant or missing id fails loud (403 / 404), not silently.
    items = []
    docs_by_id = {}
    for item in request.attachments:
        doc = await documents.get(item.document_id, actor=current_user)
        items.append((doc, item.role))
        docs_by_id[doc.id] = doc
    created = await candidates.add_attachments(candidate_id, items, actor=current_user)
    return [_attachment_response(a, docs_by_id[a.document_id]) for a in created]


@router.delete(
    "/{candidate_id}/attachments/{document_id}",
    status_code=204,
    summary="Detach a document from a candidate",
    description=(
        "Remove the link between a candidate and a document. The document "
        "itself is not deleted — it keeps its own ownership. Detaching the "
        "resume clears the candidate's resume pointer."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the candidate owner or an admin"},
        404: {"description": "Candidate or attachment not found"},
    },
)
async def remove_candidate_attachment(
    candidate_id: UUID,
    document_id: UUID,
    current_user: CurrentUser,
    candidates: CandidateServiceDep,
) -> None:
    await candidates.remove_attachment(candidate_id, document_id, actor=current_user)


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


@router.patch(
    "/applications/bulk-status",
    response_model=BulkUpdateApplicationStatusResponse,
    summary="Bulk-update application status",
    description=(
        "Apply the same status to a batch of applications in a single "
        "transaction. All-or-nothing: if any application is missing or "
        "cross-tenant, nothing is mutated and the request returns 403 / "
        "404. Response preserves request order (duplicates removed)."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the parent job's owner or an admin"},
        404: {"description": "One or more applications not found"},
    },
)
async def bulk_update_application_status(
    request: BulkUpdateApplicationStatusRequest,
    current_user: CurrentUser,
    candidates: CandidateServiceDep,
) -> BulkUpdateApplicationStatusResponse:
    apps = await candidates.bulk_update_application_status(
        request.application_ids, request.status, actor=current_user
    )
    # Preserve request order: the service returns apps in the
    # dedup'd-input order, which matches the unique ids we asked for.
    by_id = {app.id: app for app in apps}
    ordered = [
        ApplicationResponse.model_validate(by_id[aid])
        for aid in dict.fromkeys(request.application_ids)
        if aid in by_id
    ]
    return BulkUpdateApplicationStatusResponse(updated=ordered)

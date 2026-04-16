"""Job posting endpoints."""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, JobServiceDep
from app.models.job import JobStatus
from app.schemas.job import CreateJobRequest, JobResponse, UpdateJobRequest

router = APIRouter()


@router.post(
    "",
    response_model=JobResponse,
    status_code=201,
    summary="Create a job posting",
    description="Create a new job with title, description, required skills, and other criteria.",
    responses={
        401: {"description": "Not authenticated"},
        422: {"description": "Validation error"},
    },
)
async def create_job(
    request: CreateJobRequest,
    current_user: CurrentUser,
    jobs: JobServiceDep,
) -> JobResponse:
    job = await jobs.create(
        owner=current_user,
        title=request.title,
        description=request.description,
        required_skills=request.required_skills,
        preferred_skills=request.preferred_skills,
        education_level=request.education_level,
        experience_min=request.experience_min,
        experience_max=request.experience_max,
        location=request.location,
    )
    return JobResponse.model_validate(job)


@router.get(
    "",
    response_model=list[JobResponse],
    summary="List my jobs",
    description="Return jobs owned by the authenticated user, ordered by creation date.",
    responses={401: {"description": "Not authenticated"}},
)
async def list_jobs(
    current_user: CurrentUser,
    jobs: JobServiceDep,
    status: JobStatus | None = Query(None, description="Filter by job status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum jobs to return"),
    offset: int = Query(0, ge=0, description="Number of jobs to skip"),
) -> list[JobResponse]:
    result = await jobs.list_for_user(
        current_user.id, status=status, limit=limit, offset=offset
    )
    return [JobResponse.model_validate(j) for j in result]


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job details",
    description="Return details for a single job. Accessible to the owner and admins.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the job owner or an admin"},
        404: {"description": "Job not found"},
    },
)
async def get_job(
    job_id: UUID,
    current_user: CurrentUser,
    jobs: JobServiceDep,
) -> JobResponse:
    job = await jobs.get(job_id, actor=current_user)
    return JobResponse.model_validate(job)


@router.patch(
    "/{job_id}",
    response_model=JobResponse,
    summary="Update a job posting",
    description="Partially update a job. Only provided fields are changed.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the job owner or an admin"},
        404: {"description": "Job not found"},
    },
)
async def update_job(
    job_id: UUID,
    request: UpdateJobRequest,
    current_user: CurrentUser,
    jobs: JobServiceDep,
) -> JobResponse:
    updates = request.model_dump(exclude_unset=True)
    job = await jobs.update(job_id, actor=current_user, **updates)
    return JobResponse.model_validate(job)


@router.delete(
    "/{job_id}",
    status_code=204,
    summary="Delete a job posting",
    description="Permanently delete a job. Accessible to the owner and admins.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the job owner or an admin"},
        404: {"description": "Job not found"},
    },
)
async def delete_job(
    job_id: UUID,
    current_user: CurrentUser,
    jobs: JobServiceDep,
) -> None:
    await jobs.delete(job_id, actor=current_user)

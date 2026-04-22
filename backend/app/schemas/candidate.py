"""Candidate and application DTOs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.candidate import ApplicationStatus


class CandidateResponse(BaseModel):
    """A candidate derived from a processed resume."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique candidate identifier")
    owner_id: UUID = Field(..., description="Owner user ID")
    source_document_id: UUID | None = Field(
        None, description="Source resume document ID"
    )
    name: str | None = Field(
        None, description="Candidate name", examples=["Alice Smith"]
    )
    email: str | None = Field(None, description="Candidate email")
    phone: str | None = Field(None, description="Candidate phone")
    skills: list[str] = Field(..., description="Extracted skills")
    experience_years: int | None = Field(None, description="Years of experience")
    education: list[str] | None = Field(None, description="Education qualifications")
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC)")


class MatchBreakdown(BaseModel):
    """Breakdown of how the match score was computed."""

    skill_match: float = Field(
        ..., ge=0, le=1, description="Required + preferred skill overlap"
    )
    experience_fit: float = Field(
        ..., ge=0, le=1, description="Experience years vs job range"
    )
    vector_similarity: float = Field(
        ..., ge=0, le=1, description="Semantic similarity from embeddings"
    )


class ApplicationResponse(BaseModel):
    """A candidate's application to a job.

    F44.b — embeds the candidate so the job detail page renders each row
    in one round-trip (no N+1 ``getCandidate`` per row). The Application
    model auto-loads ``candidate`` via ``lazy="selectin"`` so the embed
    is free server-side.

    F44.d.6 — includes ``breakdown`` (the skill/experience/vector split
    ``MatchingService`` already persists) so the list-side hover popover
    can render "why this score" without a second endpoint.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Application ID")
    candidate_id: UUID = Field(..., description="Candidate ID")
    job_id: UUID = Field(..., description="Job ID")
    candidate: CandidateResponse = Field(
        ...,
        description=(
            "The full candidate record, embedded so the frontend can "
            "render a row (name, skills, resume link) without a second "
            "request per application."
        ),
    )
    status: ApplicationStatus = Field(
        ...,
        description="Application status (new, shortlisted, rejected, interviewed, hired)",
    )
    score: float | None = Field(None, description="Match score (0–1, higher is better)")
    breakdown: MatchBreakdown | None = Field(
        None,
        validation_alias="match_breakdown",
        description=(
            "Per-signal split that produced the score (skill overlap, "
            "experience fit, vector similarity). Null for applications "
            "that predate F44.d.6; re-running the job's match populates "
            "it."
        ),
    )
    created_at: datetime = Field(..., description="Application timestamp (UTC)")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC)")


class CandidateWithScoreResponse(CandidateResponse):
    """Candidate response enriched with match score for a specific job."""

    score: float | None = Field(None, description="Match score against the job")
    application_status: ApplicationStatus | None = Field(
        None, description="Application status for this job"
    )


class MatchResultItem(BaseModel):
    """A candidate's match result against a job."""

    candidate: CandidateResponse
    score: float = Field(..., ge=0, le=1, description="Combined match score")
    breakdown: MatchBreakdown
    application_status: ApplicationStatus = Field(..., description="Application status")


class MatchResponse(BaseModel):
    """Results of matching candidates against a job."""

    job_id: str = Field(..., description="Job that candidates were matched against")
    results: list[MatchResultItem] = Field(..., description="Ranked candidates")
    total: int = Field(..., description="Total candidates matched")


class UpdateApplicationStatusRequest(BaseModel):
    """Update an application's status."""

    status: ApplicationStatus = Field(..., description="New application status")

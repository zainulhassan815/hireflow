"""Job request and response DTOs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import JobStatus


class CreateJobRequest(BaseModel):
    """Create a new job posting."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Job title",
        examples=["Senior Python Developer"],
    )
    description: str = Field(
        ...,
        min_length=10,
        description="Full job description with responsibilities and requirements",
    )
    required_skills: list[str] = Field(
        ...,
        min_length=1,
        description="Skills required for the position",
        examples=[["Python", "FastAPI", "PostgreSQL"]],
    )
    preferred_skills: list[str] | None = Field(None, description="Nice-to-have skills")
    education_level: str | None = Field(
        None,
        description="Minimum education requirement",
        examples=["Bachelor's", "Master's"],
    )
    experience_min: int = Field(0, ge=0, description="Minimum years of experience")
    experience_max: int | None = Field(
        None, ge=0, description="Maximum years of experience"
    )
    location: str | None = Field(
        None, description="Job location", examples=["Remote", "Lahore, Pakistan"]
    )


class UpdateJobRequest(BaseModel):
    """Partially update a job posting. Only provided fields are updated."""

    title: str | None = Field(
        None, min_length=1, max_length=255, description="Job title"
    )
    description: str | None = Field(None, min_length=10, description="Job description")
    required_skills: list[str] | None = Field(
        None, min_length=1, description="Required skills"
    )
    preferred_skills: list[str] | None = Field(None, description="Preferred skills")
    education_level: str | None = Field(None, description="Education requirement")
    experience_min: int | None = Field(None, ge=0, description="Min experience years")
    experience_max: int | None = Field(None, ge=0, description="Max experience years")
    location: str | None = Field(None, description="Location")
    status: JobStatus | None = Field(None, description="Job status")


class JobResponse(BaseModel):
    """Job posting details."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique job identifier")
    owner_id: UUID = Field(..., description="ID of the user who created this job")
    title: str = Field(..., description="Job title")
    description: str = Field(..., description="Full job description")
    required_skills: list[str] = Field(..., description="Required skills")
    preferred_skills: list[str] | None = Field(None, description="Preferred skills")
    education_level: str | None = Field(None, description="Education requirement")
    experience_min: int = Field(..., description="Minimum years of experience")
    experience_max: int | None = Field(None, description="Maximum years of experience")
    location: str | None = Field(None, description="Job location")
    status: JobStatus = Field(
        ..., description="Current job status (draft, open, closed, archived)"
    )
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC)")

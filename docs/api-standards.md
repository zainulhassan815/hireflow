# API Standards - HR Screening RAG System

This document defines the standards for all FastAPI backend endpoints to ensure consistent, type-safe SDK generation via Hey API.

## Overview

**Goal:** Define backend APIs once in Python/Pydantic, auto-generate TypeScript SDK for frontend consumption.

**Type Flow:**

```md
Pydantic Model → OpenAPI 3.1 Spec → Hey API → TypeScript Types + React Query Hooks → Frontend
```

**Key Principle:** Every decision in backend API design directly affects the generated SDK quality. Be intentional.

---

## FastAPI Configuration

### Application Setup

```python
# backend/app/core/api_config.py
from fastapi import FastAPI
from fastapi.routing import APIRoute


def custom_generate_unique_id(route: APIRoute) -> str:
    """
    Generate clean operation IDs for SDK method names.
    Format: {tag}-{function_name}
    Example: documents-upload_document → SDK: documentsUploadDocument()
    """
    if route.tags:
        return f"{route.tags[0]}-{route.name}"
    return route.name


def create_app() -> FastAPI:
    return FastAPI(
        title="HR Screening RAG API",
        description="AI-Powered HR Screening and Document Retrieval System",
        version="1.0.0",
        generate_unique_id_function=custom_generate_unique_id,
        openapi_tags=[
            {"name": "auth", "description": "Authentication and user management"},
            {"name": "documents", "description": "Document upload and management"},
            {"name": "search", "description": "Semantic search and Q&A"},
            {"name": "jobs", "description": "Job posting management"},
            {"name": "resumes", "description": "Resume parsing and viewing"},
            {"name": "applications", "description": "Job applications and candidate management"},
            {"name": "email", "description": "Email integration and sync"},
            {"name": "logs", "description": "Activity logs and audit"},
        ],
    )
```

### Tags → SDK Service Mapping

Every endpoint MUST have exactly one tag. Tags determine SDK service grouping:

| Tag            | SDK Service           | Purpose                              |
| -------------- | --------------------- | ------------------------------------ |
| `auth`         | `authService`         | Login, register, password reset      |
| `documents`    | `documentsService`    | Upload, list, delete documents       |
| `search`       | `searchService`       | Semantic search, RAG Q&A             |
| `jobs`         | `jobsService`         | Job CRUD operations                  |
| `resumes`      | `resumesService`      | Resume viewing and parsing           |
| `applications` | `applicationsService` | Candidate applications, shortlisting |
| `email`        | `emailService`        | Gmail OAuth, sync, send              |
| `logs`         | `logsService`         | Activity logs                        |

```python
# Good: Single tag
@router.post("/upload", tags=["documents"])

# Bad: Multiple tags (confuses SDK grouping)
@router.post("/upload", tags=["documents", "upload"])

# Bad: No tag (goes into default group)
@router.post("/upload")
```

---

## Naming Conventions

### Models

| Type            | Pattern                     | Example                | Anti-pattern            |
| --------------- | --------------------------- | ---------------------- | ----------------------- |
| Request body    | `{Action}{Resource}Request` | `CreateJobRequest`     | `JobReq`, `NewJob`      |
| Response body   | `{Resource}Response`        | `JobResponse`          | `JobRes`, `Result`      |
| List response   | `{Resource}ListResponse`    | `DocumentListResponse` | `Documents`, `DocList`  |
| Detail response | `{Resource}DetailResponse`  | `ResumeDetailResponse` | `FullResume`            |
| Nested object   | `{Parent}{Child}`           | `ResumeEducation`      | `Education` (ambiguous) |

### Enums

Use `StrEnum` (Python 3.11+) for string enums - cleaner than `class Foo(str, Enum)`:

```python
from enum import StrEnum


class DocumentStatus(StrEnum):
    """Status of document processing"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentType(StrEnum):
    """Type of document"""
    RESUME = "resume"
    REPORT = "report"
    CONTRACT = "contract"
    LETTER = "letter"
    OTHER = "other"


class ApplicationStatus(StrEnum):
    """Status of job application"""
    NEW = "new"
    REVIEWED = "reviewed"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    INTERVIEWED = "interviewed"
    HIRED = "hired"
```

### Endpoints

| Element       | Convention          | Example                        | Anti-pattern                  |
| ------------- | ------------------- | ------------------------------ | ----------------------------- |
| Function name | `{verb}_{resource}` | `list_documents`, `create_job` | `getDocs`, `handleJob`        |
| Path params   | `{resource}_id`     | `/jobs/{job_id}`               | `/jobs/{id}`, `/jobs/{jobId}` |
| Query params  | snake_case          | `per_page`, `sort_by`          | `perPage`, `sortBy`           |
| Route prefix  | plural noun         | `/documents`, `/jobs`          | `/document`, `/job`           |

### URL Patterns

```python
# Collection endpoints
GET    /documents                    # list_documents
POST   /documents                    # upload_document

# Resource endpoints
GET    /documents/{document_id}      # get_document
DELETE /documents/{document_id}      # delete_document

# Nested resources
GET    /jobs/{job_id}/applications   # list_job_applications
POST   /jobs/{job_id}/match          # match_candidates (action)

# Actions (when CRUD doesn't fit)
POST   /search                       # search_documents
POST   /search/qa                    # ask_question
POST   /email/sync                   # sync_email
```

---

## Pydantic Model Standards

### Base Models

```python
# backend/app/schemas/base.py
from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional, List
from datetime import datetime
from uuid import UUID

T = TypeVar("T")


class BaseResponse(BaseModel):
    """Base for all response models with common fields"""
    id: UUID = Field(..., description="Unique identifier")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class ErrorDetail(BaseModel):
    """Detail for validation errors"""
    field: str = Field(..., description="Field that caused the error")
    message: str = Field(..., description="Error message")


class ErrorResponse(BaseModel):
    """Standard error response format"""
    code: str = Field(..., description="Machine-readable error code", examples=["VALIDATION_ERROR"])
    message: str = Field(..., description="Human-readable error message")
    details: Optional[List[ErrorDetail]] = Field(None, description="Field-level error details")


class PaginationMeta(BaseModel):
    """Pagination information for list responses"""
    total: int = Field(..., description="Total number of items", examples=[100])
    page: int = Field(..., description="Current page number", examples=[1])
    per_page: int = Field(..., description="Items per page", examples=[20])
    total_pages: int = Field(..., description="Total number of pages", examples=[5])


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response"""
    data: List[T]
    pagination: PaginationMeta
```

### Domain Models

```python
# backend/app/schemas/documents.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.schemas.base import BaseResponse, PaginatedResponse
from app.models.enums import DocumentStatus, DocumentType


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document"""
    document_id: UUID = Field(..., description="ID of the uploaded document")
    filename: str = Field(..., description="Original filename")
    status: DocumentStatus = Field(..., description="Processing status")
    queue_position: Optional[int] = Field(None, description="Position in processing queue")


class DocumentResponse(BaseResponse):
    """Document information"""
    filename: str = Field(..., description="Original filename")
    file_type: str = Field(..., description="File extension (pdf, docx, etc.)")
    file_size: int = Field(..., description="File size in bytes")
    doc_type: Optional[DocumentType] = Field(None, description="Detected document type")
    status: DocumentStatus = Field(..., description="Processing status")
    ocr_confidence: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="OCR confidence score (0-1)"
    )


class DocumentDetailResponse(DocumentResponse):
    """Detailed document information including extracted text"""
    extracted_text: Optional[str] = Field(None, description="Extracted text content")
    metadata: dict = Field(default_factory=dict, description="Document metadata")
    processing_error: Optional[str] = Field(None, description="Error message if processing failed")


# Type alias for paginated list
DocumentListResponse = PaginatedResponse[DocumentResponse]
```

```python
# backend/app/schemas/jobs.py
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from app.schemas.base import BaseResponse, PaginatedResponse
from app.models.enums import JobStatus


class CreateJobRequest(BaseModel):
    """Request to create a new job posting"""
    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Job title",
        examples=["Senior Python Developer"]
    )
    description: str = Field(
        ...,
        min_length=10,
        description="Job description"
    )
    required_skills: List[str] = Field(
        ...,
        min_length=1,
        description="Required skills for the position",
        examples=[["Python", "FastAPI", "PostgreSQL"]]
    )
    preferred_skills: Optional[List[str]] = Field(
        None,
        description="Preferred but not required skills"
    )
    education_level: Optional[str] = Field(
        None,
        description="Minimum education requirement",
        examples=["Bachelor's", "Master's"]
    )
    experience_min: int = Field(
        0,
        ge=0,
        description="Minimum years of experience"
    )
    experience_max: Optional[int] = Field(
        None,
        ge=0,
        description="Maximum years of experience"
    )
    location: Optional[str] = Field(
        None,
        description="Job location",
        examples=["Lahore, Pakistan"]
    )


class UpdateJobRequest(BaseModel):
    """Request to update a job posting"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=10)
    required_skills: Optional[List[str]] = Field(None, min_length=1)
    preferred_skills: Optional[List[str]] = None
    education_level: Optional[str] = None
    experience_min: Optional[int] = Field(None, ge=0)
    experience_max: Optional[int] = Field(None, ge=0)
    location: Optional[str] = None
    status: Optional[JobStatus] = None


class JobResponse(BaseResponse):
    """Job posting information"""
    title: str
    description: str
    required_skills: List[str]
    preferred_skills: List[str]
    education_level: Optional[str]
    experience_min: int
    experience_max: Optional[int]
    location: Optional[str]
    status: JobStatus
    application_count: int = Field(0, description="Number of applications received")


JobListResponse = PaginatedResponse[JobResponse]
```

```python
# backend/app/schemas/search.py
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.enums import DocumentType


class SearchRequest(BaseModel):
    """Request to search documents"""
    query: str = Field(
        ...,
        min_length=1,
        description="Natural language search query",
        examples=["Python developer with 5 years experience"]
    )
    doc_types: Optional[List[DocumentType]] = Field(
        None,
        description="Filter by document types"
    )
    date_from: Optional[datetime] = Field(
        None,
        description="Filter documents uploaded after this date"
    )
    date_to: Optional[datetime] = Field(
        None,
        description="Filter documents uploaded before this date"
    )
    limit: int = Field(10, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(0, ge=0, description="Number of results to skip")


class SearchHighlight(BaseModel):
    """Highlighted text match"""
    text: str = Field(..., description="Text snippet with match")
    chunk_index: int = Field(..., description="Index of the chunk in document")


class SearchResultItem(BaseModel):
    """Single search result"""
    document_id: UUID
    filename: str
    doc_type: Optional[DocumentType]
    relevance_score: float = Field(..., ge=0, le=1, description="Relevance score (0-1)")
    highlights: List[SearchHighlight]
    metadata: dict = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Search results"""
    results: List[SearchResultItem]
    total: int = Field(..., description="Total matching documents")
    query_time_ms: int = Field(..., description="Query execution time in milliseconds")


class AskQuestionRequest(BaseModel):
    """Request to ask a question using RAG"""
    question: str = Field(
        ...,
        min_length=1,
        description="Question about documents",
        examples=["What skills does John Doe have?"]
    )
    document_ids: Optional[List[UUID]] = Field(
        None,
        description="Limit to specific documents (None = search all)"
    )
    max_context_chunks: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum context chunks to retrieve"
    )


class AnswerSource(BaseModel):
    """Source document for an answer"""
    document_id: UUID
    filename: str
    chunk_index: int
    relevance: float = Field(..., ge=0, le=1)


class AskQuestionResponse(BaseModel):
    """Response to a question"""
    answer: str = Field(..., description="AI-generated answer")
    confidence: float = Field(..., ge=0, le=1, description="Answer confidence score")
    sources: List[AnswerSource] = Field(..., description="Source documents used")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
```

```python
# backend/app/schemas/applications.py
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.schemas.base import BaseResponse, PaginatedResponse
from app.models.enums import ApplicationStatus


class MatchBreakdown(BaseModel):
    """Breakdown of candidate match score"""
    skill_match: float = Field(..., ge=0, le=1, description="Skill match score")
    experience_match: float = Field(..., ge=0, le=1, description="Experience match score")
    education_match: float = Field(..., ge=0, le=1, description="Education match score")


class MatchCandidatesRequest(BaseModel):
    """Request to match candidates to a job"""
    resume_ids: Optional[List[UUID]] = Field(
        None,
        description="Specific resumes to match (None = all resumes)"
    )
    min_score: float = Field(
        0.5,
        ge=0,
        le=1,
        description="Minimum match score threshold"
    )
    limit: int = Field(50, ge=1, le=200, description="Maximum candidates to return")


class CandidateMatchResult(BaseModel):
    """Result of matching a candidate to a job"""
    resume_id: UUID
    candidate_name: str
    email: Optional[str]
    match_score: float = Field(..., ge=0, le=1)
    breakdown: MatchBreakdown
    matched_skills: List[str]
    missing_skills: List[str]


class MatchCandidatesResponse(BaseModel):
    """Response with matched candidates"""
    matches: List[CandidateMatchResult]
    total_matched: int
    processing_time_ms: int


class UpdateApplicationStatusRequest(BaseModel):
    """Request to update application status"""
    status: ApplicationStatus
    notes: Optional[str] = Field(None, max_length=1000, description="Optional notes")


class ApplicationResponse(BaseResponse):
    """Job application information"""
    job_id: UUID
    resume_id: UUID
    candidate_name: str
    email: Optional[str]
    match_score: Optional[float]
    breakdown: Optional[MatchBreakdown]
    status: ApplicationStatus
    notes: Optional[str]
    reviewed_by: Optional[UUID]
    reviewed_at: Optional[datetime]


ApplicationListResponse = PaginatedResponse[ApplicationResponse]
```

---

## Endpoint Implementation

### Standard Endpoint Template

```python
# backend/app/api/v1/jobs.py
from fastapi import APIRouter, HTTPException, status, Query, Path, Depends
from typing import Optional
from uuid import UUID

from app.schemas.jobs import (
    CreateJobRequest,
    UpdateJobRequest,
    JobResponse,
    JobListResponse,
)
from app.schemas.applications import (
    MatchCandidatesRequest,
    MatchCandidatesResponse,
    ApplicationListResponse,
)
from app.schemas.base import ErrorResponse
from app.models.enums import JobStatus
from app.services.job_service import JobService
from app.api.deps import get_current_user, get_job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "",
    response_model=JobListResponse,
    summary="List jobs",
    description="Get a paginated list of job postings with optional filtering",
)
async def list_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[JobStatus] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search in title/description"),
    service: JobService = Depends(get_job_service),
) -> JobListResponse:
    """List all job postings with pagination."""
    return await service.list_jobs(
        page=page,
        per_page=per_page,
        status=status,
        search=search,
    )


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create job",
    description="Create a new job posting",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
async def create_job(
    request: CreateJobRequest,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    """Create a new job posting."""
    return await service.create_job(request)


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job",
    description="Get job posting details",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def get_job(
    job_id: UUID = Path(..., description="Job ID"),
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    """Get job by ID."""
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Job not found"}
        )
    return job


@router.put(
    "/{job_id}",
    response_model=JobResponse,
    summary="Update job",
    description="Update an existing job posting",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def update_job(
    job_id: UUID = Path(..., description="Job ID"),
    request: UpdateJobRequest = ...,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    """Update job posting."""
    return await service.update_job(job_id, request)


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete job",
    description="Delete a job posting",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def delete_job(
    job_id: UUID = Path(..., description="Job ID"),
    service: JobService = Depends(get_job_service),
) -> None:
    """Delete job posting."""
    await service.delete_job(job_id)


@router.post(
    "/{job_id}/match",
    response_model=MatchCandidatesResponse,
    summary="Match candidates",
    description="Match and rank candidates against job requirements using AI",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def match_candidates(
    job_id: UUID = Path(..., description="Job ID"),
    request: MatchCandidatesRequest = ...,
    service: JobService = Depends(get_job_service),
) -> MatchCandidatesResponse:
    """Match candidates to job using AI scoring."""
    return await service.match_candidates(job_id, request)


@router.get(
    "/{job_id}/applications",
    response_model=ApplicationListResponse,
    summary="List job applications",
    description="Get all applications for a specific job",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def list_job_applications(
    job_id: UUID = Path(..., description="Job ID"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[ApplicationStatus] = Query(None),
    sort_by: str = Query("match_score", description="Sort field"),
    order: str = Query("desc", description="Sort order"),
    service: JobService = Depends(get_job_service),
) -> ApplicationListResponse:
    """List applications for a job."""
    return await service.list_applications(
        job_id=job_id,
        page=page,
        per_page=per_page,
        status=status,
        sort_by=sort_by,
        order=order,
    )
```

---

## Error Handling

### Standard Error Codes

| Code                     | HTTP Status | Description                          |
| ------------------------ | ----------- | ------------------------------------ |
| `VALIDATION_ERROR`       | 400/422     | Invalid input data                   |
| `UNAUTHORIZED`           | 401         | Authentication required              |
| `FORBIDDEN`              | 403         | Insufficient permissions             |
| `NOT_FOUND`              | 404         | Resource not found                   |
| `ALREADY_EXISTS`         | 409         | Resource already exists              |
| `FILE_TOO_LARGE`         | 413         | Uploaded file exceeds limit          |
| `UNSUPPORTED_FILE_TYPE`  | 415         | File type not allowed                |
| `RATE_LIMITED`           | 429         | Too many requests                    |
| `PROCESSING_FAILED`      | 500         | Document/AI processing failed        |
| `EXTERNAL_SERVICE_ERROR` | 502         | External service (Gmail, LLM) failed |
| `INTERNAL_ERROR`         | 500         | Unexpected server error              |

### Custom Exception Classes

```python
# backend/app/core/exceptions.py
from fastapi import HTTPException, status


class NotFoundError(HTTPException):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": f"{resource} not found",
                "details": [{"field": "id", "message": f"{resource} with id {resource_id} does not exist"}]
            }
        )


class ValidationError(HTTPException):
    def __init__(self, message: str, field: str = None):
        details = [{"field": field, "message": message}] if field else None
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": message,
                "details": details
            }
        )


class ProcessingError(HTTPException):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "PROCESSING_FAILED",
                "message": message
            }
        )
```

---

## SDK Generation

### Hey API Configuration

```typescript
// frontend/openapi-ts.config.ts
import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  client: "@hey-api/client-fetch",
  input: "./openapi.json",
  output: {
    path: "./src/api/generated",
    format: "prettier",
    lint: "eslint",
  },
  plugins: [
    "@hey-api/typescript",
    "@hey-api/sdk",
    {
      name: "@hey-api/transformers",
      dates: true, // Transform datetime strings to Date objects
    },
    {
      name: "@tanstack/react-query",
      // Generates React Query hooks automatically
    },
  ],
});
```

### Generation Scripts

```bash
#!/bin/bash
# scripts/generate-api.sh
set -e

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"

echo "Fetching OpenAPI spec from $BACKEND_URL..."
curl -s "$BACKEND_URL/openapi.json" -o frontend/openapi.json

echo "Preprocessing OpenAPI spec..."
node scripts/preprocess-openapi.js

echo "Generating TypeScript SDK..."
cd frontend && pnpm exec openapi-ts

echo "SDK generation complete!"
```

```javascript
// scripts/preprocess-openapi.js
const fs = require("fs");
const spec = JSON.parse(fs.readFileSync("frontend/openapi.json", "utf8"));

// Remove tag prefix from operation IDs for cleaner SDK methods
// "jobs-list_jobs" → "listJobs"
for (const pathData of Object.values(spec.paths)) {
  for (const operation of Object.values(pathData)) {
    if (operation.operationId && operation.tags?.[0]) {
      const prefix = `${operation.tags[0]}-`;
      if (operation.operationId.startsWith(prefix)) {
        operation.operationId = operation.operationId.slice(prefix.length);
      }
    }
  }
}

fs.writeFileSync("frontend/openapi.json", JSON.stringify(spec, null, 2));
console.log("Preprocessed OpenAPI spec");
```

### Frontend Usage Examples

```typescript
// Using generated SDK with React Query
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  jobsListJobs,
  jobsCreateJob,
  jobsMatchCandidates,
  searchSearchDocuments,
  searchAskQuestion,
} from "@/api/generated";
import type {
  CreateJobRequest,
  JobResponse,
  SearchRequest,
  AskQuestionRequest,
} from "@/api/generated";

// List jobs with pagination
export function useJobs(page: number = 1, status?: JobStatus) {
  return useQuery({
    queryKey: ["jobs", { page, status }],
    queryFn: () => jobsListJobs({ query: { page, per_page: 20, status } }),
  });
}

// Create job mutation
export function useCreateJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateJobRequest) => jobsCreateJob({ body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

// Match candidates
export function useMatchCandidates(jobId: string) {
  return useMutation({
    mutationFn: (request: MatchCandidatesRequest) =>
      jobsMatchCandidates({
        path: { job_id: jobId },
        body: request,
      }),
  });
}

// Semantic search
export function useSearch() {
  return useMutation({
    mutationFn: (request: SearchRequest) =>
      searchSearchDocuments({ body: request }),
  });
}

// RAG Q&A
export function useAskQuestion() {
  return useMutation({
    mutationFn: (request: AskQuestionRequest) =>
      searchAskQuestion({ body: request }),
  });
}
```

```tsx
// Component usage
function JobsPage() {
  const { data, isLoading, error } = useJobs(1);
  const createJob = useCreateJob();

  if (isLoading) return <Spinner />;
  if (error) return <Error message={error.message} />;

  const handleCreate = async (formData: CreateJobRequest) => {
    try {
      await createJob.mutateAsync(formData);
      toast.success("Job created!");
    } catch (err) {
      // err is typed as ErrorResponse
      toast.error(err.message);
    }
  };

  return (
    <div>
      {data?.data.map((job) => (
        <JobCard key={job.id} job={job} />
      ))}
      <Pagination meta={data?.pagination} />
    </div>
  );
}
```

---

## Checklist for New Endpoints

Before creating a new endpoint, verify:

- [ ] Single tag assigned (determines SDK service grouping)
- [ ] Function name follows `{verb}_{resource}` pattern
- [ ] Path params use `{resource}_id` naming
- [ ] Query params use snake_case
- [ ] Request model ends with `Request`
- [ ] Response model ends with `Response`
- [ ] All fields have `Field()` with description
- [ ] Examples provided for key fields
- [ ] Proper types used (UUID, datetime, Enum - not raw strings)
- [ ] Error responses documented in `responses={}`
- [ ] Summary and description provided
- [ ] HTTP status codes are correct (201 for create, 204 for delete)
- [ ] Regenerate SDK and verify TypeScript types

---

## Package Versions

### Backend

```md
fastapi>=0.109.0
pydantic>=2.5.0
python>=3.11
```

### Frontend

```md
@hey-api/client-fetch: ^0.4.0
@hey-api/openapi-ts: ^0.54.0
@tanstack/react-query: ^5.0.0
```

---

## References

- [FastAPI Generate Clients](https://fastapi.tiangolo.com/advanced/generate-clients/)
- [Hey API Documentation](https://heyapi.dev/)
- [Pydantic V2 Documentation](https://docs.pydantic.dev/latest/)
- [TanStack Query](https://tanstack.com/query/latest)

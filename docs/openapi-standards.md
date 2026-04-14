# OpenAPI & Schema Standards

Every endpoint and Pydantic schema must produce a self-documenting OpenAPI spec.
A developer reading only the Swagger UI or the generated TypeScript SDK should
understand every field, every error, and every constraint — without reading
Python source.

## Guiding principles

1. **The spec IS the documentation.** If it's not in the OpenAPI JSON, it doesn't
   exist for frontend consumers.
2. **Every field gets a `Field(description=...)`** — no bare type annotations on
   response/request models.
3. **Every route gets a `summary` and `description`** on the decorator — summary
   is the short label (< 60 chars), description is the full explanation.
4. **Error responses are declared** via `responses={...}` on the decorator so the
   spec lists every status code the endpoint can return.
5. **Use `examples` (plural, dict form) on `Field()`** for rich OpenAPI 3.1
   examples. Use `json_schema_extra={"example": ...}` on the model class for
   a single-object example.

---

## Schema checklist

```python
class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique document identifier")
    owner_id: UUID = Field(..., description="ID of the user who uploaded this document")
    filename: str = Field(..., description="Original filename at upload time", examples=["resume.pdf"])
    mime_type: str = Field(..., description="MIME type", examples=["application/pdf"])
    size_bytes: int = Field(..., description="File size in bytes", examples=[204800])
    status: DocumentStatus = Field(..., description="Processing pipeline status")
```

Rules enforced:

| Rule | Example |
|------|---------|
| Every field has `description` | `Field(..., description="...")` |
| Numeric fields have `examples` | `examples=[204800]` |
| String fields have `examples` when format isn't obvious | `examples=["resume.pdf"]` |
| Python-internal names are aliased | `metadata_` → `serialization_alias="metadata"` |
| Enums carry their own `description` via the class docstring | `class DocumentStatus(StrEnum): """Processing pipeline status."""` |
| `from_attributes=True` on every ORM-backed response | `model_config = ConfigDict(from_attributes=True)` |

---

## Route checklist

```python
@router.post(
    "",
    response_model=DocumentResponse,
    status_code=201,
    summary="Upload a document",
    description=(
        "Upload a PDF, DOCX, DOC, PNG, JPEG, or TIFF file. "
        "The file is stored in object storage and queued for text extraction. "
        "Maximum size: configurable via MAX_FILE_SIZE_MB (default 10 MB)."
    ),
    responses={
        401: {"description": "Not authenticated"},
        413: {"description": "File exceeds size limit"},
        415: {"description": "Unsupported file type"},
    },
)
```

Rules enforced:

| Rule | Why |
|------|-----|
| `summary` is ≤ 60 chars, imperative mood | Becomes the method label in Swagger and the SDK JSDoc one-liner |
| `description` explains behaviour, constraints, side effects | Frontend devs read this instead of Python source |
| `responses` lists every non-2xx status code the endpoint can return | SDK can type error branches; Swagger shows them in the UI |
| `status_code` is explicit for non-200 | 201 for create, 204 for delete — don't rely on FastAPI default |
| `response_model` is always set (except for raw `Response` returns) | Drives the generated TypeScript type |

---

## Error response shape

All domain errors return:

```json
{"detail": "Human-readable message."}
```

This matches FastAPI's built-in `HTTPException` shape so the frontend has one
error-handling path. The mapping from domain error class → HTTP status code
lives in `api/error_handlers.py`.

Declare error responses on routes using the status codes from this table:

| Domain error | HTTP | When |
|--------------|------|------|
| `InvalidCredentials` | 401 | Wrong email/password |
| `InvalidToken` | 401 | Expired/revoked/malformed token |
| `AccountDisabled` | 403 | User exists but is deactivated |
| `Forbidden` | 403 | Role/ownership check failed |
| `NotFound` | 404 | Resource doesn't exist |
| `EmailAlreadyRegistered` | 409 | Duplicate registration |
| `FileTooLarge` | 413 | Upload exceeds size limit |
| `UnsupportedFileType` | 415 | MIME type not in allowed set |

---

## Naming conventions

| Type | Pattern | Example |
|------|---------|---------|
| Request body | `{Action}{Resource}Request` | `RegisterRequest`, `ResetPasswordRequest` |
| Response body | `{Resource}Response` | `UserResponse`, `DocumentResponse` |
| List wrapper | `list[{Resource}Response]` or `PaginatedResponse[{Resource}Response]` | — |
| Enum | `{Resource}{Dimension}` as `StrEnum` | `DocumentStatus`, `DocumentType` |
| Route function | `{verb}_{resource}` | `upload_document`, `list_documents` |
| Path param | `{resource}_id` | `/documents/{document_id}` |
| Query param | `snake_case` | `per_page`, `sort_by` |

---

## OpenAPI tags

Defined once in `main.py`. Each tag maps 1:1 to a frontend SDK service.

```python
openapi_tags = [
    {
        "name": "auth",
        "description": "Registration, login, token refresh, logout, and password reset.",
    },
    {
        "name": "users",
        "description": "User administration (admin only).",
    },
    {
        "name": "documents",
        "description": "Document upload, listing, download, and deletion.",
    },
    ...
]
```

Every router is mounted with exactly one tag via `tags=["documents"]` on the
`include_router` call. Never set tags on individual route decorators — the
router-level tag is the single source of truth.

---

## SDK generation flow

```
Pydantic schema (with Field descriptions)
    → FastAPI generates OpenAPI 3.1 JSON
        → hey-api/openapi-ts generates TypeScript types + SDK methods
            → Frontend imports from @/api
```

Every `Field(description=...)` becomes a JSDoc comment on the generated type.
Every `summary` becomes the method's JSDoc one-liner. Every `responses` entry
becomes a typed error union. This is why the spec quality matters — it's the
**only** documentation the frontend developer sees.

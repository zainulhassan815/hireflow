"""Document management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Query, UploadFile
from fastapi.responses import Response

from app.api.deps import CurrentUser, DocumentServiceDep
from app.schemas.document import DocumentResponse
from app.worker.tasks import extract_document_text

router = APIRouter()


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=201,
    summary="Upload a document",
    description=(
        "Upload a PDF, DOCX, DOC, PNG, JPEG, or TIFF file. "
        "The file is stored in object storage and queued for text extraction. "
        "Maximum file size is controlled by the MAX_FILE_SIZE_MB setting "
        "(default 10 MB). Returns the document metadata with status 'pending'."
    ),
    responses={
        401: {"description": "Not authenticated"},
        413: {"description": "File exceeds the configured size limit"},
        415: {"description": "File MIME type is not in the allowed set"},
    },
)
async def upload_document(
    file: UploadFile,
    current_user: CurrentUser,
    documents: DocumentServiceDep,
) -> DocumentResponse:
    data = await file.read()
    doc = await documents.upload(
        owner=current_user,
        filename=file.filename or "untitled",
        mime_type=file.content_type or "application/octet-stream",
        data=data,
    )
    extract_document_text.delay(str(doc.id))
    return DocumentResponse.model_validate(doc)


@router.get(
    "",
    response_model=list[DocumentResponse],
    summary="List my documents",
    description=(
        "Return documents owned by the authenticated user, "
        "ordered by upload date (newest first). "
        "Supports limit/offset pagination."
    ),
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def list_documents(
    current_user: CurrentUser,
    documents: DocumentServiceDep,
    limit: int = Query(50, ge=1, le=100, description="Maximum documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip"),
) -> list[DocumentResponse]:
    docs = await documents.list_for_user(current_user.id, limit=limit, offset=offset)
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document metadata",
    description=(
        "Return metadata for a single document. "
        "Accessible to the document owner and admins."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the document owner or an admin"},
        404: {"description": "Document not found"},
    },
)
async def get_document(
    document_id: UUID,
    current_user: CurrentUser,
    documents: DocumentServiceDep,
) -> DocumentResponse:
    doc = await documents.get(document_id, actor=current_user)
    return DocumentResponse.model_validate(doc)


@router.get(
    "/{document_id}/download",
    summary="Download document content",
    description=(
        "Download the raw file bytes. The response Content-Type matches the "
        "original upload MIME type and Content-Disposition triggers a browser "
        "download with the original filename."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the document owner or an admin"},
        404: {"description": "Document not found"},
    },
)
async def download_document(
    document_id: UUID,
    current_user: CurrentUser,
    documents: DocumentServiceDep,
) -> Response:
    doc, data = await documents.download(document_id, actor=current_user)
    return Response(
        content=data,
        media_type=doc.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.delete(
    "/{document_id}",
    status_code=204,
    summary="Delete a document",
    description=(
        "Remove the document record and its object-storage blob. "
        "Accessible to the document owner and admins. This action is irreversible."
    ),
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not the document owner or an admin"},
        404: {"description": "Document not found"},
    },
)
async def delete_document(
    document_id: UUID,
    current_user: CurrentUser,
    documents: DocumentServiceDep,
) -> None:
    await documents.delete(document_id, actor=current_user)

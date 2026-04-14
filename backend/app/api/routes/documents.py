"""Document management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Query, UploadFile
from fastapi.responses import Response

from app.api.deps import CurrentUser, DocumentServiceDep
from app.schemas.document import DocumentResponse

router = APIRouter()


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile,
    current_user: CurrentUser,
    documents: DocumentServiceDep,
) -> DocumentResponse:
    """Upload a document (PDF, DOCX, DOC, PNG, JPEG, TIFF)."""
    data = await file.read()
    doc = await documents.upload(
        owner=current_user,
        filename=file.filename or "untitled",
        mime_type=file.content_type or "application/octet-stream",
        data=data,
    )
    return DocumentResponse.model_validate(doc)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    current_user: CurrentUser,
    documents: DocumentServiceDep,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[DocumentResponse]:
    """List documents owned by the current user."""
    docs = await documents.list_for_user(current_user.id, limit=limit, offset=offset)
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    current_user: CurrentUser,
    documents: DocumentServiceDep,
) -> DocumentResponse:
    """Get document metadata."""
    doc = await documents.get(document_id, actor=current_user)
    return DocumentResponse.model_validate(doc)


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    current_user: CurrentUser,
    documents: DocumentServiceDep,
) -> Response:
    """Download the document's raw bytes."""
    doc, data = await documents.download(document_id, actor=current_user)
    return Response(
        content=data,
        media_type=doc.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    current_user: CurrentUser,
    documents: DocumentServiceDep,
) -> None:
    """Delete a document (blob + DB row)."""
    await documents.delete(document_id, actor=current_user)

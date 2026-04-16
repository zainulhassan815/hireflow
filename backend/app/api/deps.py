"""FastAPI dependencies and composition root.

This is the one place that binds concrete adapter implementations to their
`Protocol` abstractions and wires services together. Every route and every
service reaches for things through the annotated aliases defined here.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.argon2_hasher import Argon2Hasher
from app.adapters.chroma_store import ChromaVectorStore
from app.adapters.email_sender import LoggingEmailSender
from app.adapters.jwt_token_issuer import JwtTokenIssuer
from app.adapters.llm.registry import get_llm_provider
from app.adapters.minio_storage import MinioBlobStorage
from app.adapters.protocols import (
    BlobStorage,
    EmailSender,
    PasswordHasher,
    ResetTokenStore,
    RevocationStore,
    TokenIssuer,
    TokenType,
    VectorStore,
)
from app.adapters.reset_token_store import RedisResetTokenStore
from app.adapters.revocation_store import RedisRevocationStore
from app.core.config import settings
from app.core.db import get_db
from app.core.redis import get_redis
from app.domain.exceptions import InvalidToken
from app.models import User, UserRole
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository
from app.services.auth_service import AuthService
from app.services.document_service import DocumentService
from app.services.password_reset_service import PasswordResetService
from app.services.rag_service import RagService
from app.services.search_service import SearchService
from app.services.session_service import SessionService
from app.services.user_service import UserService

_logger = logging.getLogger(__name__)

# ---------- HTTP primitives ----------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)

DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]


# ---------- Singletons (stateless adapters) ----------

_hasher = Argon2Hasher()
_token_issuer = JwtTokenIssuer(
    secret=settings.jwt_secret_key,
    algorithm=settings.jwt_algorithm,
    access_ttl=timedelta(minutes=settings.jwt_access_token_expire_minutes),
    refresh_ttl=timedelta(days=settings.jwt_refresh_token_expire_days),
)
_email_sender = LoggingEmailSender()
_blob_storage = MinioBlobStorage(
    endpoint=settings.storage_endpoint,
    access_key=settings.storage_access_key,
    secret_key=settings.storage_secret_key,
    bucket=settings.storage_bucket,
    region=settings.storage_region,
)

try:
    _vector_store: VectorStore | None = ChromaVectorStore(
        host=settings.chroma_host, port=settings.chroma_port
    )
except Exception:
    _logger.warning("ChromaDB unavailable at startup; vector search disabled")
    _vector_store = None

_llm_provider = get_llm_provider(settings)
if _llm_provider:
    _logger.info("LLM provider: %s", _llm_provider.model_name)


# ---------- Adapter providers ----------


def get_password_hasher() -> PasswordHasher:
    return _hasher


def get_token_issuer() -> TokenIssuer:
    return _token_issuer


def get_email_sender() -> EmailSender:
    return _email_sender


def get_revocation_store(redis: RedisDep) -> RevocationStore:
    return RedisRevocationStore(redis)


def get_reset_token_store(redis: RedisDep) -> ResetTokenStore:
    return RedisResetTokenStore(redis)


def get_vector_store() -> VectorStore | None:
    return _vector_store


def get_blob_storage() -> BlobStorage:
    return _blob_storage


# ---------- Repository providers ----------


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)


def get_document_repository(db: DbSession) -> DocumentRepository:
    return DocumentRepository(db)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
DocumentRepositoryDep = Annotated[DocumentRepository, Depends(get_document_repository)]


# ---------- Service providers ----------


def get_auth_service(
    users: UserRepositoryDep,
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> AuthService:
    return AuthService(users, hasher)


def get_session_service(
    users: UserRepositoryDep,
    tokens: Annotated[TokenIssuer, Depends(get_token_issuer)],
    revocation: Annotated[RevocationStore, Depends(get_revocation_store)],
) -> SessionService:
    return SessionService(users, tokens, revocation)


def get_password_reset_service(
    users: UserRepositoryDep,
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[ResetTokenStore, Depends(get_reset_token_store)],
    email: Annotated[EmailSender, Depends(get_email_sender)],
) -> PasswordResetService:
    return PasswordResetService(
        users,
        hasher,
        tokens,
        email,
        token_ttl_seconds=settings.password_reset_token_expire_minutes * 60,
    )


def get_user_service(users: UserRepositoryDep) -> UserService:
    return UserService(users)


def get_document_service(
    documents: DocumentRepositoryDep,
    storage: Annotated[BlobStorage, Depends(get_blob_storage)],
) -> DocumentService:
    return DocumentService(
        documents,
        storage,
        max_file_size_bytes=settings.max_file_size_mb * 1024 * 1024,
        vector_store=_vector_store,
    )


def get_search_service(documents: DocumentRepositoryDep) -> SearchService:
    return SearchService(documents, _vector_store)


def get_rag_service(documents: DocumentRepositoryDep) -> RagService | None:
    if _vector_store is None or _llm_provider is None:
        return None
    return RagService(documents, _vector_store, _llm_provider)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
PasswordResetServiceDep = Annotated[
    PasswordResetService, Depends(get_password_reset_service)
]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
RagServiceDep = Annotated[RagService | None, Depends(get_rag_service)]


# ---------- Auth context ----------


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    users: UserRepositoryDep,
    tokens: Annotated[TokenIssuer, Depends(get_token_issuer)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = tokens.decode(token, TokenType.ACCESS)
    except InvalidToken as exc:
        raise unauthorized from exc
    user_id: UUID = payload.sub
    user = await users.get(user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ---------- Role gates (HTTP layer defense-in-depth) ----------


def require_role(*allowed: UserRole):
    async def _checker(current_user: CurrentUser) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _checker


RequireAdmin = Annotated[User, Depends(require_role(UserRole.ADMIN))]

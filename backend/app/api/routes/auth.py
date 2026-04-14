from uuid import UUID

import jwt
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, RedisDep
from app.core.config import settings
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    token_remaining_ttl,
)
from app.models import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import authenticate_user, register_user
from app.services.email import send_password_reset_email
from app.services.password_reset import consume_reset_token, issue_reset_token
from app.services.token_revocation import is_jti_revoked, revoke_jti

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(request: RegisterRequest, db: DbSession) -> UserResponse:
    """Register a new user."""
    user = await register_user(
        db,
        email=request.email,
        password=request.password,
        full_name=request.full_name,
    )
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: DbSession) -> TokenResponse:
    """Exchange email + password for access and refresh tokens."""
    user = await authenticate_user(db, email=request.email, password=request.password)
    return TokenResponse(
        access_token=create_access_token(user.id, {"role": user.role.value}),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest, db: DbSession, redis: RedisDep
) -> TokenResponse:
    """Rotate a refresh token: revoke it and issue a new access + refresh pair."""
    payload = await _validate_refresh_token(request.refresh_token, redis)

    user = await db.get(User, UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise _invalid_refresh_token()

    # Rotate: revoke the presented refresh token so it can't be reused.
    await revoke_jti(redis, payload["jti"], token_remaining_ttl(payload))

    return TokenResponse(
        access_token=create_access_token(user.id, {"role": user.role.value}),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: RefreshRequest, redis: RedisDep) -> None:
    """Revoke the caller's refresh token. Idempotent for expired/invalid tokens."""
    try:
        payload = decode_token(request.refresh_token, TokenType.REFRESH)
    except jwt.InvalidTokenError:
        # A token we can't decode can't do any harm; treat logout as successful.
        return
    await revoke_jti(redis, payload["jti"], token_remaining_ttl(payload))


def _invalid_refresh_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token.",
    )


async def _validate_refresh_token(token: str, redis: RedisDep) -> dict:
    try:
        payload = decode_token(token, TokenType.REFRESH)
    except jwt.InvalidTokenError as exc:
        raise _invalid_refresh_token() from exc
    if await is_jti_revoked(redis, payload["jti"]):
        raise _invalid_refresh_token()
    return payload


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    request: ForgotPasswordRequest, db: DbSession, redis: RedisDep
) -> None:
    """Send a password-reset link if an account with the email exists.

    Always returns 204 regardless of whether the email matches a user, so the
    endpoint can't be used to enumerate registered accounts.
    """
    result = await db.execute(select(User).where(User.email == request.email.lower()))
    user = result.scalar_one_or_none()
    if user is not None and user.is_active:
        token = await issue_reset_token(
            redis,
            user.id,
            ttl_seconds=settings.password_reset_token_expire_minutes * 60,
        )
        reset_url = f"/reset-password?token={token}"
        await send_password_reset_email(user.email, reset_url)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    request: ResetPasswordRequest, db: DbSession, redis: RedisDep
) -> None:
    """Consume a reset token and set a new password."""
    user_id = await consume_reset_token(redis, request.token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )
    user.hashed_password = hash_password(request.new_password)
    await db.commit()


@router.get("/me", response_model=UserResponse)
async def read_me(current_user: CurrentUser) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse.model_validate(current_user)

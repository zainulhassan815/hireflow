from fastapi import APIRouter, status

from app.api.deps import (
    AuthServiceDep,
    CurrentUser,
    PasswordResetServiceDep,
    SessionServiceDep,
)
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(request: RegisterRequest, auth: AuthServiceDep) -> UserResponse:
    """Register a new user."""
    user = await auth.register(
        email=request.email,
        password=request.password,
        full_name=request.full_name,
    )
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest, auth: AuthServiceDep, session: SessionServiceDep
) -> TokenResponse:
    """Exchange email + password for access and refresh tokens."""
    user = await auth.authenticate(email=request.email, password=request.password)
    pair = session.issue(user)
    return TokenResponse(access_token=pair.access, refresh_token=pair.refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest, session: SessionServiceDep
) -> TokenResponse:
    """Rotate a refresh token: revoke it and issue a new pair."""
    pair = await session.refresh(request.refresh_token)
    return TokenResponse(access_token=pair.access, refresh_token=pair.refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: RefreshRequest, session: SessionServiceDep) -> None:
    """Revoke the caller's refresh token."""
    await session.logout(request.refresh_token)


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    request: ForgotPasswordRequest, reset: PasswordResetServiceDep
) -> None:
    """Send a password-reset link. Always 204 regardless of account existence."""
    await reset.request_reset(request.email)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    request: ResetPasswordRequest, reset: PasswordResetServiceDep
) -> None:
    """Consume a reset token and set a new password."""
    await reset.reset(request.token, request.new_password)


@router.get("/me", response_model=UserResponse)
async def read_me(current_user: CurrentUser) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse.model_validate(current_user)

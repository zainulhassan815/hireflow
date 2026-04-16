from fastapi import APIRouter, Request, status

from app.api.deps import (
    ActivityServiceDep,
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
from app.schemas.profile import ChangePasswordRequest, UpdateProfileRequest

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    summary="Register a new account",
    description=(
        "Create a new user with the HR role. "
        "Returns the created user profile (no tokens — call /login next)."
    ),
    responses={
        409: {"description": "Email already registered"},
        422: {"description": "Validation error (e.g. password too short)"},
    },
)
async def register(request: RegisterRequest, auth: AuthServiceDep) -> UserResponse:
    user = await auth.register(
        email=request.email,
        password=request.password,
        full_name=request.full_name,
    )
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in",
    description=(
        "Exchange email + password for a short-lived access token and "
        "a long-lived refresh token. The access token must be sent as "
        "`Authorization: Bearer <token>` on subsequent requests."
    ),
    responses={
        401: {"description": "Invalid email or password"},
        403: {"description": "Account is disabled"},
    },
)
async def login(
    request: LoginRequest,
    http_request: Request,
    auth: AuthServiceDep,
    session: SessionServiceDep,
    activity: ActivityServiceDep,
) -> TokenResponse:
    user = await auth.authenticate(email=request.email, password=request.password)
    pair = session.issue(user)
    await activity.log(
        actor_id=user.id,
        action="login",
        detail=f"Login from {request.email}",
        ip_address=http_request.client.host if http_request.client else None,
    )
    return TokenResponse(access_token=pair.access, refresh_token=pair.refresh)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh tokens",
    description=(
        "Present a valid refresh token to receive a new access + refresh pair. "
        "The old refresh token is revoked (rotation) and cannot be reused."
    ),
    responses={
        401: {"description": "Invalid, expired, or already-revoked refresh token"},
    },
)
async def refresh_token(
    request: RefreshRequest, session: SessionServiceDep
) -> TokenResponse:
    pair = await session.refresh(request.refresh_token)
    return TokenResponse(access_token=pair.access, refresh_token=pair.refresh)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out",
    description=(
        "Revoke the presented refresh token so it can no longer be used to "
        "obtain new access tokens. Idempotent for expired or invalid tokens."
    ),
)
async def logout(request: RefreshRequest, session: SessionServiceDep) -> None:
    await session.logout(request.refresh_token)


@router.post(
    "/forgot-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Request password reset",
    description=(
        "Send a password-reset link to the given email if an active account "
        "exists. Always returns 204 regardless of whether the email is "
        "registered, so this endpoint cannot be used for account enumeration."
    ),
)
async def forgot_password(
    request: ForgotPasswordRequest, reset: PasswordResetServiceDep
) -> None:
    await reset.request_reset(request.email)


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset password",
    description=(
        "Consume a one-time reset token (received via email) and set a new "
        "password. The token is single-use and expires after 15 minutes."
    ),
    responses={
        401: {"description": "Invalid or expired reset token"},
        422: {"description": "Validation error (e.g. password too short)"},
    },
)
async def reset_password(
    request: ResetPasswordRequest, reset: PasswordResetServiceDep
) -> None:
    await reset.reset(request.token, request.new_password)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Return the profile of the currently authenticated user.",
    responses={
        401: {"description": "Not authenticated or token expired"},
    },
)
async def read_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update profile",
    description="Update the current user's name or email.",
    responses={
        401: {"description": "Not authenticated"},
        409: {"description": "Email already taken"},
    },
)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: CurrentUser,
    auth: AuthServiceDep,
) -> UserResponse:
    user = await auth.update_profile(
        current_user,
        full_name=request.full_name,
        email=request.email,
    )
    return UserResponse.model_validate(user)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change password",
    description="Change the current user's password. Requires the current password for verification.",
    responses={
        401: {"description": "Current password is incorrect"},
    },
)
async def change_password(
    request: ChangePasswordRequest,
    current_user: CurrentUser,
    auth: AuthServiceDep,
) -> None:
    await auth.change_password(
        current_user,
        current_password=request.current_password,
        new_password=request.new_password,
    )

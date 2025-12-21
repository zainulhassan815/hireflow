from fastapi import APIRouter

from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(request: RegisterRequest) -> UserResponse:
    """Register a new user."""
    # TODO: Implement registration
    raise NotImplementedError


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest) -> TokenResponse:
    """Login and receive access/refresh tokens."""
    # TODO: Implement login
    raise NotImplementedError


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token() -> TokenResponse:
    """Refresh access token using refresh token."""
    # TODO: Implement token refresh
    raise NotImplementedError


@router.post("/logout", status_code=204)
async def logout() -> None:
    """Logout and invalidate tokens."""
    # TODO: Implement logout
    raise NotImplementedError

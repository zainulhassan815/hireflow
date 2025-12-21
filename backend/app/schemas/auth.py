from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Request to register a new user."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    name: str = Field(..., min_length=1, max_length=100, description="Full name")


class LoginRequest(BaseModel):
    """Request to login."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="Password")


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")


class UserResponse(BaseModel):
    """User response."""

    id: str = Field(..., description="User ID")
    email: EmailStr = Field(..., description="User email")
    name: str = Field(..., description="User name")

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    """Create a new user account."""

    email: EmailStr = Field(
        ..., description="User email address", examples=["hr@company.com"]
    )
    password: str = Field(
        ...,
        min_length=8,
        description="Password (minimum 8 characters)",
        examples=["s3cur3P@ss"],
    )
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User's full name",
        examples=["Jane Smith"],
    )


class LoginRequest(BaseModel):
    """Exchange credentials for access and refresh tokens."""

    email: EmailStr = Field(
        ..., description="Registered email address", examples=["hr@company.com"]
    )
    password: str = Field(..., description="Account password")


class RefreshRequest(BaseModel):
    """Rotate a refresh token for a new token pair."""

    refresh_token: str = Field(..., description="Valid, non-revoked JWT refresh token")


class ForgotPasswordRequest(BaseModel):
    """Request a password-reset link via email."""

    email: EmailStr = Field(
        ...,
        description="Email address of the account to reset",
        examples=["hr@company.com"],
    )


class ResetPasswordRequest(BaseModel):
    """Set a new password using a one-time reset token."""

    token: str = Field(..., description="One-time reset token received via email")
    new_password: str = Field(
        ...,
        min_length=8,
        description="New password (minimum 8 characters)",
        examples=["n3wS3cur3P@ss"],
    )


class TokenResponse(BaseModel):
    """JWT token pair returned on login or refresh."""

    access_token: str = Field(
        ..., description="Short-lived JWT for authenticating API requests"
    )
    refresh_token: str = Field(
        ...,
        description="Long-lived JWT used to obtain a new access token",
    )
    token_type: str = Field(
        default="bearer", description="Token scheme (always 'bearer')"
    )


class UserResponse(BaseModel):
    """Public user profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique user identifier")
    email: EmailStr = Field(..., description="User email address")
    full_name: str | None = Field(
        None, description="User's full name", examples=["Jane Smith"]
    )
    role: UserRole = Field(..., description="Authorization role (hr or admin)")
    is_active: bool = Field(..., description="Whether the account is enabled")

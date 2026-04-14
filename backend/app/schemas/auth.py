from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    full_name: str = Field(..., min_length=1, max_length=255, description="Full name")


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="Password")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="JWT refresh token")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="Account email address")


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., description="One-time reset token from the email link")
    new_password: str = Field(
        ..., min_length=8, description="New password (min 8 characters)"
    )


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str | None
    role: UserRole
    is_active: bool

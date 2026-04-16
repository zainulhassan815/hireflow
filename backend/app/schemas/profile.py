"""Profile and settings DTOs."""

from pydantic import BaseModel, EmailStr, Field


class UpdateProfileRequest(BaseModel):
    """Update the current user's profile."""

    full_name: str | None = Field(
        None, min_length=1, max_length=255, description="Full name"
    )
    email: EmailStr | None = Field(None, description="New email address")


class ChangePasswordRequest(BaseModel):
    """Change the current user's password."""

    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(
        ..., min_length=8, description="New password (minimum 8 characters)"
    )

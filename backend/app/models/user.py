from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.encryption import EncryptedString
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(StrEnum):
    HR = "hr"
    ADMIN = "admin"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=UserRole.HR,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

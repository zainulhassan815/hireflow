"""Symmetric encryption for at-rest sensitive fields.

Uses Fernet (AES-128-CBC + HMAC-SHA256, authenticated) via
``cryptography.fernet``. Multiple keys are supported through
``MultiFernet`` so rotation works without downtime: prepend a new key to
``ENCRYPTION_KEYS``, new writes use the first key, reads try each key
in order.

The only public surface is the ``EncryptedString`` SQLAlchemy type. Model
columns declare it exactly like ``String`` — the TypeDecorator encrypts
on write and decrypts on read transparently.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

from app.core.config import settings


@lru_cache(maxsize=1)
def get_cipher() -> MultiFernet:
    """Return the app-wide ``MultiFernet`` built from ``ENCRYPTION_KEYS``.

    Called at startup to fail-fast on missing keys; called on every
    encrypt/decrypt via ``EncryptedString``. Cached.
    """
    keys = settings.encryption_keys
    if not keys:
        raise RuntimeError(
            "ENCRYPTION_KEYS is required. Generate with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    return MultiFernet([Fernet(k.get_secret_value().encode()) for k in keys])


class EncryptedString(TypeDecorator[str]):
    """A ``str | None`` column stored as Fernet ciphertext bytes in Postgres."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> bytes | None:
        if value is None:
            return None
        return get_cipher().encrypt(value.encode("utf-8"))

    def process_result_value(self, value: bytes | None, dialect: object) -> str | None:
        if value is None:
            return None
        return get_cipher().decrypt(bytes(value)).decode("utf-8")

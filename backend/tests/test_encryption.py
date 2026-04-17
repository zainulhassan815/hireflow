"""EncryptedString round-trips and keeps ciphertext out of plaintext DB.

If this test stops passing, it means either:

* The Fernet cipher is no longer wired into the TypeDecorator
  (silent plaintext leak — catastrophic for PII columns), or
* Key rotation/loading regressed (boot appears fine but reads fail).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models import User

pytestmark = pytest.mark.asyncio


async def test_encrypted_full_name_round_trips(admin_user) -> None:
    """Write through ORM, read through ORM — plaintext in, plaintext out."""
    async with SessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.id == admin_user.id))
        ).scalar_one()
        assert user.full_name == "Test Admin"


async def test_raw_db_contains_ciphertext_not_plaintext(admin_user) -> None:
    """Bypass the ORM; raw column holds Fernet-style bytes, not the plaintext.

    Would have caught a regression where ``EncryptedString`` silently
    passes-through the plaintext bytes (e.g. a bad migration that
    made the column plain ``String`` again).
    """
    async with SessionLocal() as session:
        raw = await session.scalar(
            text("SELECT full_name FROM users WHERE id = :uid").bindparams(
                uid=admin_user.id
            )
        )
    assert raw is not None
    # Fernet's v1 token format always starts with 0x80 (ASCII '€' when
    # mis-decoded) → base64url → leading bytes 'gAAAAA'. We just assert
    # the stored bytes are not the plaintext we wrote.
    assert b"Test Admin" not in bytes(raw)
    # And that it's long enough to plausibly be ciphertext (Fernet adds
    # ~57 bytes of overhead + base64 expansion).
    assert len(bytes(raw)) > 50


async def test_get_cipher_raises_without_keys(monkeypatch) -> None:
    """Missing ``ENCRYPTION_KEYS`` must fail loudly, not silently no-op.

    We can't realistically re-trigger the ``create_app`` fail-fast
    without rebuilding the app; test the underlying helper directly,
    which is what ``create_app`` calls.
    """
    from app.core import encryption as enc

    # Clear the lru_cache so our override is observed.
    enc.get_cipher.cache_clear()
    monkeypatch.setattr(enc.settings, "encryption_keys", [])

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEYS"):
        enc.get_cipher()

    enc.get_cipher.cache_clear()

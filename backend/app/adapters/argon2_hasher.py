"""Argon2id password hasher adapter."""

from __future__ import annotations

from argon2 import PasswordHasher as _ArgonHasher
from argon2.exceptions import VerifyMismatchError


class Argon2Hasher:
    """`PasswordHasher` protocol implementation using argon2-cffi defaults.

    OWASP's recommended algorithm for new systems. Parameters are the library
    defaults (m=64 MiB, t=3, p=4 as of argon2-cffi 23.x); call
    `needs_rehash` on each verify and rehash on login to transparently
    upgrade stored hashes when these tighten.
    """

    def __init__(self) -> None:
        self._impl = _ArgonHasher()

    def hash(self, password: str) -> str:
        return self._impl.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            self._impl.verify(password_hash, password)
        except VerifyMismatchError:
            return False
        return True

    def needs_rehash(self, password_hash: str) -> bool:
        return self._impl.check_needs_rehash(password_hash)

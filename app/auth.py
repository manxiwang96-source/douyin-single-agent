from __future__ import annotations

import hashlib
import hmac
import os
import secrets

PBKDF2_SCHEME = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 390_000
SESSION_DAYS = 7
MIN_PASSWORD_LENGTH = 8


class AuthError(Exception):
    """Base class for authentication failures."""


class InvalidPasswordError(AuthError):
    """Password failed local policy checks."""


class InvalidCredentialsError(AuthError):
    """login_name or password did not match."""


def hash_password(password: str, *, iterations: int | None = None) -> str:
    if not isinstance(password, str) or not password:
        raise InvalidPasswordError("password is required")
    rounds = DEFAULT_ITERATIONS if iterations is None else iterations
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"{PBKDF2_SCHEME}${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    if not password or not encoded:
        return False
    parts = encoded.split("$")
    if len(parts) != 4 or parts[0] != PBKDF2_SCHEME:
        return False
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidPasswordError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return password


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

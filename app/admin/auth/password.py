"""Password hashing and policy enforcement.

Uses the ``bcrypt`` library directly (without passlib's wrapper). bcrypt
remains the OWASP-recommended scheme for password storage; the cost
factor is taken from ``admin_settings.bcrypt_rounds`` (default 12 ≈
250 ms on modern hardware).

We deliberately do NOT use passlib: it has been unmaintained since
2020 (last release 1.7.4) and its bcrypt backend breaks with
``bcrypt >= 4.1`` during an internal startup self-test that uses a
72+ byte probe string the new bcrypt rejects strictly.

bcrypt has a hard 72-byte input limit. Passwords longer than that are
rejected at policy time so the failure surfaces inline on the form
instead of as a ValueError from the underlying library.

Policy violations raise ``PasswordPolicyError`` with the human-readable
reason; the admin UI catches this and displays the message on the
form. ``MAX_PASSWORD_BYTES`` is documented so the constant can be
referred to by the form template and the CLI prompt help text.
"""
from __future__ import annotations

import string

import bcrypt

from app.admin.config import admin_settings


class PasswordPolicyError(ValueError):
    """Raised when a candidate password violates the policy."""


# bcrypt's algorithm hard-limit. Stored here so callers (templates,
# CLI, tests) can reference a single source of truth.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt at the configured cost.

    Returns the standard bcrypt MCF string (``$2b$<cost>$<salt+hash>``).
    """
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > MAX_PASSWORD_BYTES:
        raise PasswordPolicyError(
            f"Password must not exceed {MAX_PASSWORD_BYTES} bytes (utf-8). "
            f"Got {len(pw_bytes)} bytes."
        )
    salt = bcrypt.gensalt(rounds=admin_settings.bcrypt_rounds)
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plaintext: str, password_hash: str | None) -> bool:
    """Constant-time verification. Always returns False for empty/invalid hash."""
    if not password_hash:
        return False
    try:
        pw_bytes = plaintext.encode("utf-8")
        if len(pw_bytes) > MAX_PASSWORD_BYTES:
            # bcrypt would reject anyway — short-circuit so we don't
            # raise from the underlying lib on a normal login attempt.
            return False
        return bcrypt.checkpw(pw_bytes, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed hash in the DB — treat as no match, don't leak details.
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash's cost factor is below current policy."""
    # bcrypt MCF: $2[abxy]$<cost>$<22-char salt><31-char hash>
    try:
        parts = password_hash.split("$")
        if len(parts) < 4:
            return True
        current_cost = int(parts[2])
    except (ValueError, IndexError):
        return True
    return current_cost < admin_settings.bcrypt_rounds


def validate_password_policy(password: str) -> None:
    """Raise ``PasswordPolicyError`` if ``password`` violates policy.

    Policy is configured in ``admin_settings``. Keeping it centralised
    means the same rules apply to the create-user form, the
    change-password form, and any future bulk-import path.
    """
    cfg = admin_settings
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > MAX_PASSWORD_BYTES:
        raise PasswordPolicyError(
            f"Password must not exceed {MAX_PASSWORD_BYTES} bytes (utf-8). "
            f"Got {len(pw_bytes)} bytes."
        )
    if len(password) < cfg.password_min_length:
        raise PasswordPolicyError(
            f"Password must be at least {cfg.password_min_length} characters."
        )
    if cfg.password_require_mixed_case and (
        password.lower() == password or password.upper() == password
    ):
        raise PasswordPolicyError(
            "Password must contain both upper- and lower-case letters."
        )
    if cfg.password_require_digit and not any(ch.isdigit() for ch in password):
        raise PasswordPolicyError("Password must contain at least one digit.")
    if cfg.password_require_symbol and not any(
        ch in string.punctuation for ch in password
    ):
        raise PasswordPolicyError("Password must contain at least one symbol.")

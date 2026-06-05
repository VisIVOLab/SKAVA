"""Local username/password authentication backend.

Looks up a user by username (case-insensitive), verifies the bcrypt
hash, and updates ``last_login_at`` on success. Returns the persisted
``User`` instance on success or ``None`` on failure — callers must not
distinguish "unknown user" from "wrong password" in the response (to
avoid username enumeration).

Future OIDC backend will live in ``oidc.py`` and expose the same
``authenticate()`` shape so the calling router code stays unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.auth.password import needs_rehash, hash_password, verify_password
from app.models.user import User


def authenticate(
    db: Session, *, username: str, password: str
) -> User | None:
    """Verify credentials and return the user on success.

    On success, also:
    * sets ``last_login_at`` on the user row
    * rehashes the password if the stored hash's cost factor is below
      the current policy

    Both side effects are committed in the same transaction the caller
    holds; pass an ``autocommit=False`` session (the default).
    """
    if not username or not password:
        return None

    stmt = select(User).where(
        func.lower(User.username) == username.strip().lower()
    )
    user = db.scalar(stmt)
    if user is None or not user.is_active:
        # Always do a dummy hash op so timing does not leak existence.
        verify_password(password, "$2b$12$invalidinvalidinvalidinvaliduvw")
        return None

    if not verify_password(password, user.password_hash):
        return None

    user.last_login_at = datetime.now(timezone.utc)
    if needs_rehash(user.password_hash or ""):
        user.password_hash = hash_password(password)
    db.flush()
    return user

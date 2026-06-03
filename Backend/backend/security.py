"""All JWT, password-hashing, and token-blacklist logic lives here.

Routers never build or decode tokens directly — they call these helpers. This
keeps the security primitives (algorithm, lifetimes, rotation, blacklist) in one
auditable place.

Token model:
* Access  — 15-minute HS256 JWT, payload ``{sub, jti, iat, exp, type:"access"}``.
* Refresh — 7-day opaque JWT, stored only as a bcrypt hash in ``user_sessions``.
* Refresh rotation revokes the old session row on every refresh.
* Revoked access JTIs are tracked in an in-memory set plus the ``audit_log`` for
  durability hints; protected requests reject blacklisted JTIs.
"""

from __future__ import annotations

import datetime as dt
import uuid

from jose import JWTError, jwt

from .config import get_settings

_settings = get_settings()

# In-memory blacklist of revoked access-token JTIs. Repopulated on restart from
# still-valid revoked sessions; access tokens are short-lived (15 min) so the
# window of risk after a restart is minimal.
_revoked_jtis: set[str] = set()


# --- Password / refresh-token hashing --------------------------------------
# We use the ``bcrypt`` library directly rather than passlib's CryptContext:
# passlib 1.7.4 runs a self-test at first use that feeds bcrypt a >72-byte probe,
# which bcrypt 5.x rejects with a ValueError. Calling bcrypt directly avoids that
# broken probe. Refresh tokens are first reduced to a 64-char SHA-256 hex digest
# (well under bcrypt's 72-byte limit) before hashing.
def _digest(secret: str) -> bytes:
    """Return a stable 64-byte SHA-256 hex digest of ``secret`` (bcrypt-safe)."""
    import hashlib

    return hashlib.sha256(secret.encode("utf-8")).hexdigest().encode("ascii")


def hash_secret(secret: str) -> str:
    """Return a bcrypt hash of ``secret`` (used for refresh tokens)."""
    import bcrypt

    return bcrypt.hashpw(_digest(secret), bcrypt.gensalt()).decode("ascii")


def verify_secret(secret: str, hashed: str) -> bool:
    """Verify ``secret`` against a stored bcrypt ``hashed`` value."""
    import bcrypt

    try:
        return bcrypt.checkpw(_digest(secret), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def token_tail(token: str) -> str:
    """Return only the last 8 chars of a token (safe for logging)."""
    return token[-8:] if token else ""


# --- JWT creation ----------------------------------------------------------
def create_access_token(user_id: int) -> tuple[str, str]:
    """Create a signed access token.

    Args:
        user_id: The subject user ID.

    Returns:
        ``(token, jti)`` — the encoded JWT and its unique JWT ID.
    """
    now = dt.datetime.now(dt.timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "iat": now,
        "exp": now + dt.timedelta(minutes=_settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    token = jwt.encode(payload, _settings.JWT_SECRET, algorithm=_settings.JWT_ALGORITHM)
    return token, jti


def create_refresh_token(user_id: int) -> tuple[str, dt.datetime]:
    """Create a signed refresh token.

    Args:
        user_id: The subject user ID.

    Returns:
        ``(token, expires_at)``.
    """
    now = dt.datetime.now(dt.timezone.utc)
    expires_at = now + dt.timedelta(days=_settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expires_at,
        "type": "refresh",
    }
    token = jwt.encode(payload, _settings.JWT_REFRESH_SECRET, algorithm=_settings.JWT_ALGORITHM)
    return token, expires_at


# --- JWT verification ------------------------------------------------------
def decode_access_token(token: str) -> dict:
    """Decode and validate an access token.

    Args:
        token: The bearer JWT.

    Returns:
        The decoded claims.

    Raises:
        JWTError: If the signature/expiry is invalid, the type is wrong, or the
            JTI has been revoked.
    """
    payload = jwt.decode(token, _settings.JWT_SECRET, algorithms=[_settings.JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise JWTError("Wrong token type")
    if payload.get("jti") in _revoked_jtis:
        raise JWTError("Token revoked")
    return payload


def decode_refresh_token(token: str) -> dict:
    """Decode and validate a refresh token's signature/expiry/type.

    Args:
        token: The refresh JWT.

    Returns:
        The decoded claims.

    Raises:
        JWTError: If invalid or not a refresh token.
    """
    payload = jwt.decode(token, _settings.JWT_REFRESH_SECRET, algorithms=[_settings.JWT_ALGORITHM])
    if payload.get("type") != "refresh":
        raise JWTError("Wrong token type")
    return payload


# --- Blacklist -------------------------------------------------------------
def revoke_jti(jti: str) -> None:
    """Add an access-token JTI to the in-memory blacklist."""
    if jti:
        _revoked_jtis.add(jti)


def is_jti_revoked(jti: str) -> bool:
    """Return whether an access-token JTI is blacklisted."""
    return jti in _revoked_jtis

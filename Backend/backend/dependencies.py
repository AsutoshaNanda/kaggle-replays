"""FastAPI dependency-injection helpers: DB sessions, current user, rate limiting.

The ``limiter`` defined here is shared by ``main.py`` (registration) and the
routers (decorators). Rate-limit violations are persisted to ``audit_log`` with
``status="blocked"`` via :func:`rate_limit_exceeded_handler`.
"""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends, Header, HTTPException, Request, status
from jose import JWTError
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .audit import write_audit
from .config import get_settings
from .database import AsyncSessionLocal
from .models import User
from .security import decode_access_token

_settings = get_settings()


# --- DB session ------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async DB session, rolling back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# --- Authentication --------------------------------------------------------
def _extract_bearer(authorization: str | None) -> str:
    """Return the bearer token from an ``Authorization`` header, or raise 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization.split(" ", 1)[1].strip()


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve and return the authenticated :class:`User` from the access token.

    Raises:
        HTTPException: 401 if the token is missing/invalid/revoked or the user is
            unknown or inactive.
    """
    token = _extract_bearer(authorization)
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


# --- Rate limiting ---------------------------------------------------------
def _rate_key(request: Request) -> str:
    """Rate-limit key: authenticated user ID if available, else client IP."""
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        try:
            payload = decode_access_token(auth.split(" ", 1)[1].strip())
            return f"user:{payload['sub']}"
        except JWTError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_rate_key, default_limits=[_settings.GLOBAL_RATE_LIMIT])


async def rate_limit_exceeded_handler(request: Request, exc) -> "JSONResponse":
    """Handle slowapi ``RateLimitExceeded``: audit + 429 with ``Retry-After``.

    Args:
        request: The throttled request.
        exc: The ``RateLimitExceeded`` instance.

    Returns:
        A 429 JSON response carrying a ``Retry-After`` header.
    """
    from starlette.responses import JSONResponse

    ip = request.client.host if request.client else "unknown"
    async with AsyncSessionLocal() as db:
        await write_audit(
            db,
            action="ratelimit.blocked",
            ip_address=ip,
            status="blocked",
            resource_type="endpoint",
            resource_id=request.url.path,
            user_agent=request.headers.get("user-agent"),
            detail={"limit": str(getattr(exc, "detail", "exceeded"))},
        )
    response = JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Too many requests"},
    )
    response.headers["Retry-After"] = "60"
    return response

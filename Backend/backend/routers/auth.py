"""Authentication endpoints: Kaggle login flow, refresh, logout, current user.

Login model: the backend manages a per-user Playwright ``auth.json`` (created by
the existing ``login.py`` flow). ``/auth/kaggle-login`` returns the URL the user
opens to authenticate; ``/auth/kaggle-callback`` finalizes by reading the saved
session, creating the user, and issuing tokens. Refresh tokens are delivered as
httponly, secure, SameSite=Strict cookies — JS never sees them.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit
from ..config import get_settings
from ..dependencies import get_current_user, get_db, limiter
from ..kaggle_service import decode_client_token
from ..models import User
from ..schemas import (
    KaggleLoginResponse,
    MessageResponse,
    ProfileUpdate,
    TokenResponse,
    UserResponse,
)
from ..security import decode_access_token, decode_refresh_token
from ..services import auth_service
from ..session_manager import get_session_manager

router = APIRouter(prefix="/auth", tags=["auth"])
_settings = get_settings()
_REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Attach the refresh token as a hardened httponly cookie."""
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/auth",
        max_age=_settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
    )


def _frontend_base() -> str:
    """Return the configured frontend origin (first allowed CORS origin)."""
    origins = _settings.allowed_origins_list
    return origins[0] if origins else "http://localhost:5173"


def _login_error_redirect(message: str) -> RedirectResponse:
    """Redirect to the frontend login page with a human-friendly error message."""
    from urllib.parse import quote

    return RedirectResponse(url=f"{_frontend_base()}/login?error={quote(message)}", status_code=302)


@router.post("/kaggle-login", response_model=KaggleLoginResponse)
@limiter.limit("5/15minutes")
async def kaggle_login(request: Request, db: AsyncSession = Depends(get_db)) -> KaggleLoginResponse:
    """Return the URL the user opens to authenticate their Kaggle session.

    In local dev (``DEV_LOGIN_ENABLED``) this points at ``/auth/dev-login`` which
    logs in using the local ``auth.json``; otherwise it points at Kaggle.
    """
    ip = request.state.client_ip
    await write_audit(db, action="auth.login_initiated", ip_address=ip, status="success")
    if _settings.DEV_LOGIN_ENABLED:
        base = str(request.base_url).rstrip("/")
        return KaggleLoginResponse(redirect_url=f"{base}/auth/dev-login")
    return KaggleLoginResponse(redirect_url="https://www.kaggle.com/account/login")


@router.get("/dev-login")
async def dev_login(request: Request, db: AsyncSession = Depends(get_db)):
    """LOCAL DEV ONLY: log in using the project-root ``auth.json``.

    Reads the existing Playwright session, identifies the user from its
    ``CLIENT-TOKEN``, stages it under ``sessions/{user_id}/auth.json`` (so live
    Kaggle calls work), issues tokens, sets the refresh cookie, and redirects
    into the frontend. Disabled unless ``DEV_LOGIN_ENABLED`` is true.
    """
    if not _settings.DEV_LOGIN_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    ip = request.state.client_ip
    source = Path("auth.json").resolve()
    if not source.exists() or source.stat().st_size == 0:
        await write_audit(db, action="auth.login", ip_address=ip, status="failure")
        return _login_error_redirect(
            "No Kaggle session found. Run `python login.py` in the Backend folder to connect."
        )

    identity = decode_client_token(source)
    if not identity.get("kaggle_user"):
        await write_audit(db, action="auth.login", ip_address=ip, status="failure")
        return _login_error_redirect(
            "Could not read your Kaggle identity. Re-run `python login.py` to refresh the session."
        )

    user = await auth_service.upsert_user(
        db,
        identity["kaggle_user"],
        identity.get("display_name"),
        thumbnail_url=identity.get("thumbnail_url"),
        profile_url=identity.get("profile_url"),
        tier=identity.get("tier"),
    )

    # Stage the session at sessions/{user_id}/auth.json (0600) for live API calls.
    staged = get_session_manager().session_path(user.id)
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(source.read_bytes())
    os.chmod(staged, 0o600)

    await auth_service.link_playwright_session(db, user.id, str(staged))
    access, refresh = await auth_service.issue_tokens(db, user, ip, request.headers.get("user-agent"))
    await write_audit(db, action="auth.login", ip_address=ip, status="success", user_id=user.id)

    frontend = _settings.allowed_origins_list[0] if _settings.allowed_origins_list else "http://localhost:5173"
    redirect = RedirectResponse(url=f"{frontend}/login#access_token={access}", status_code=302)
    _set_refresh_cookie(redirect, refresh)
    return redirect


@router.get("/kaggle-callback", response_model=TokenResponse)
@limiter.limit("5/15minutes")
async def kaggle_callback(
    request: Request, response: Response, user_token: str | None = None, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Finalize login: read the saved session, upsert the user, issue tokens.

    ``user_token`` identifies which staged session directory to read (the numeric
    user slot the desktop ``login.py`` wrote ``auth.json`` into).
    """
    ip = request.state.client_ip
    manager = get_session_manager()
    slot = user_token or "0"
    try:
        path = manager.session_path(int(slot)) if slot.isdigit() else None
    except (ValueError, TypeError):
        path = None
    if path is None or not path.exists():
        await write_audit(db, action="auth.login", ip_address=ip, status="failure")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No staged Kaggle session found")

    identity = decode_client_token(path)
    if not identity.get("kaggle_user"):
        await write_audit(db, action="auth.login", ip_address=ip, status="failure")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read Kaggle identity")

    user = await auth_service.upsert_user(
        db,
        identity["kaggle_user"],
        identity.get("display_name"),
        thumbnail_url=identity.get("thumbnail_url"),
        profile_url=identity.get("profile_url"),
        tier=identity.get("tier"),
    )
    await auth_service.link_playwright_session(db, user.id, str(path))
    access, refresh = await auth_service.issue_tokens(db, user, ip, request.headers.get("user-agent"))
    _set_refresh_cookie(response, refresh)
    await write_audit(db, action="auth.login", ip_address=ip, status="success", user_id=user.id)
    return TokenResponse(access_token=access)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("5/15minutes")
async def refresh(
    request: Request, response: Response, refresh_token: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Rotate the refresh token and return a fresh access token."""
    ip = request.state.client_ip
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    try:
        user_id = int(decode_refresh_token(refresh_token)["sub"])
    except (JWTError, KeyError, ValueError):
        await write_audit(db, action="auth.refresh", ip_address=ip, status="failure")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    new_refresh = await auth_service.rotate_refresh(db, user_id, refresh_token)
    if new_refresh is None:
        await write_audit(db, action="auth.refresh", ip_address=ip, status="failure", user_id=user_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token not recognized")
    from ..security import create_access_token

    access, _ = create_access_token(user_id)
    _set_refresh_cookie(response, new_refresh)
    await write_audit(db, action="auth.refresh", ip_address=ip, status="success", user_id=user_id)
    return TokenResponse(access_token=access)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Revoke the current refresh token + access JTI and clear the cookie."""
    ip = request.state.client_ip
    access_jti, user_id = None, None
    if authorization and authorization.lower().startswith("bearer "):
        try:
            claims = decode_access_token(authorization.split(" ", 1)[1].strip())
            access_jti, user_id = claims.get("jti"), int(claims["sub"])
        except (JWTError, KeyError, ValueError):
            pass
    if user_id is not None and refresh_token:
        await auth_service.revoke_session(db, user_id, refresh_token, access_jti)
    response.delete_cookie(_REFRESH_COOKIE, path="/auth")
    await write_audit(db, action="auth.logout", ip_address=ip, status="success", user_id=user_id)
    return MessageResponse(message="logged out")


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the authenticated user's public profile."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update the user's locally-editable display name (Kaggle handle is fixed)."""
    current_user.display_name = body.display_name.strip()
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)

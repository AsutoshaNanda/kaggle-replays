"""Auth service logic: user upsert, session issuance, rotation, revocation.

Keeps the auth router thin. All JWT primitives come from :mod:`backend.security`.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import PlaywrightSession, User, UserSession
from ..security import (
    create_access_token,
    create_refresh_token,
    hash_secret,
    revoke_jti,
    verify_secret,
)

_settings = get_settings()


async def upsert_user(
    db: AsyncSession,
    kaggle_user: str,
    display_name: str | None,
    thumbnail_url: str | None = None,
    profile_url: str | None = None,
    tier: str | None = None,
) -> User:
    """Create or update a user by Kaggle handle; stamp ``last_login``.

    Kaggle-imported profile fields (avatar/profile/tier) refresh on each login.
    A locally-edited ``display_name`` is preserved on update.
    """
    user = (await db.execute(select(User).where(User.kaggle_user == kaggle_user))).scalar_one_or_none()
    now = dt.datetime.now(dt.timezone.utc)
    if user is None:
        user = User(
            kaggle_user=kaggle_user,
            display_name=display_name,
            thumbnail_url=thumbnail_url,
            profile_url=profile_url,
            tier=tier,
            last_login=now,
        )
        db.add(user)
    else:
        user.display_name = user.display_name or display_name
        if thumbnail_url:
            user.thumbnail_url = thumbnail_url
        if profile_url:
            user.profile_url = profile_url
        if tier:
            user.tier = tier
        user.last_login = now
    await db.flush()
    return user


async def link_playwright_session(db: AsyncSession, user_id: int, session_path: str) -> None:
    """Record (or update) the per-user ``auth.json`` path."""
    existing = (
        await db.execute(select(PlaywrightSession).where(PlaywrightSession.user_id == user_id))
    ).scalar_one_or_none()
    if existing is None:
        db.add(PlaywrightSession(user_id=user_id, session_path=session_path, last_used=dt.datetime.now(dt.timezone.utc)))
    else:
        existing.session_path = session_path
        existing.is_valid = True
        existing.last_used = dt.datetime.now(dt.timezone.utc)
    await db.flush()


async def _enforce_session_cap(db: AsyncSession, user_id: int) -> None:
    """Revoke the oldest active session if the per-user cap is reached."""
    active = (
        await db.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked.is_(False))
            .order_by(UserSession.created_at.asc())
        )
    ).scalars().all()
    if len(active) >= _settings.MAX_SESSIONS_PER_USER:
        for old in active[: len(active) - _settings.MAX_SESSIONS_PER_USER + 1]:
            old.revoked = True
            old.revoked_at = dt.datetime.now(dt.timezone.utc)
    await db.flush()


async def issue_tokens(db: AsyncSession, user: User, ip: str | None, user_agent: str | None) -> tuple[str, str]:
    """Issue an access+refresh pair, enforcing the concurrent-session cap.

    Returns:
        ``(access_token, refresh_token)``.
    """
    await _enforce_session_cap(db, user.id)
    access, _ = create_access_token(user.id)
    refresh, expires_at = create_refresh_token(user.id)
    db.add(
        UserSession(
            user_id=user.id,
            refresh_token=hash_secret(refresh),
            ip_address=(ip or "")[:45] or None,
            user_agent=(user_agent or "")[:500] or None,
            expires_at=expires_at,
        )
    )
    await db.commit()
    return access, refresh


async def rotate_refresh(db: AsyncSession, user_id: int, presented: str) -> str | None:
    """Validate + rotate a refresh token; return a new one or ``None``.

    The matching active session is revoked and replaced (rotation). Returns
    ``None`` if no matching, unexpired, unrevoked session exists.
    """
    now = dt.datetime.now(dt.timezone.utc)
    candidates = (
        await db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.revoked.is_(False),
                UserSession.expires_at > now,
            )
        )
    ).scalars().all()
    match = next((s for s in candidates if verify_secret(presented, s.refresh_token)), None)
    if match is None:
        return None
    match.revoked = True
    match.revoked_at = now
    new_refresh, expires_at = create_refresh_token(user_id)
    db.add(
        UserSession(
            user_id=user_id,
            refresh_token=hash_secret(new_refresh),
            ip_address=match.ip_address,
            user_agent=match.user_agent,
            expires_at=expires_at,
        )
    )
    await db.commit()
    return new_refresh


async def revoke_session(db: AsyncSession, user_id: int, presented: str, access_jti: str | None) -> None:
    """Revoke the session matching ``presented`` and blacklist the access JTI."""
    if access_jti:
        revoke_jti(access_jti)
    candidates = (
        await db.execute(
            select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked.is_(False))
        )
    ).scalars().all()
    match = next((s for s in candidates if verify_secret(presented, s.refresh_token)), None)
    if match is not None:
        match.revoked = True
        match.revoked_at = dt.datetime.now(dt.timezone.utc)
    await db.commit()

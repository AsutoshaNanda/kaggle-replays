"""Audit-log writer — the single entry point for immutable security events.

Every auth attempt, download action, and rate-limit block is recorded here with
``status`` of ``success`` / ``failure`` / ``blocked``. ``detail`` must never
contain PII or secrets.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    ip_address: str,
    status: str = "success",
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    user_agent: str | None = None,
    detail: dict | None = None,
    commit: bool = True,
) -> None:
    """Insert one audit-log row.

    Args:
        db: Active async session.
        action: Dotted action name, e.g. ``"auth.login"``.
        ip_address: Client IP (required).
        status: ``"success"``, ``"failure"``, or ``"blocked"``.
        user_id: Acting user, or ``None`` for unauthenticated events.
        resource_type: Optional resource category.
        resource_id: Optional resource identifier (Kaggle ID or job UUID).
        user_agent: Optional client user-agent.
        detail: Optional JSON-serializable context (no PII/secrets).
        commit: Whether to commit immediately (use ``False`` inside a larger txn).
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500] or None,
        status=status,
        detail=detail,
    )
    db.add(entry)
    if commit:
        await db.commit()

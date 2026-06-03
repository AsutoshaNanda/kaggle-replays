"""Input sanitization helpers shared across routers and workers."""

from __future__ import annotations

import re

_SLUG_RE = re.compile(r"^[a-z0-9-]{1,200}$")
_FILENAME_CLEAN_RE = re.compile(r"[^A-Za-z0-9_-]")


def is_valid_slug(slug: str) -> bool:
    """Return ``True`` if ``slug`` matches the competition-slug pattern.

    Args:
        slug: Candidate competition slug.

    Returns:
        Whether ``slug`` is 1–200 chars of ``[a-z0-9-]``.
    """
    return bool(_SLUG_RE.match(slug or ""))


def safe_component(name: str) -> str:
    """Sanitize a string for safe use as a single path component.

    Strips known archive/script extensions, replaces spaces with underscores,
    and removes any character outside ``[A-Za-z0-9_-]``.

    Args:
        name: Raw name (e.g. a submission title).

    Returns:
        A non-empty sanitized component (falls back to ``"unnamed"``).
    """
    name = name or ""
    for ext in (".tar.gz", ".zip", ".py"):
        if name.endswith(ext):
            name = name[: -len(ext)]
            break
    name = name.replace(" ", "_")
    return _FILENAME_CLEAN_RE.sub("", name) or "unnamed"


def sanitize_error(message: str, limit: int = 300) -> str:
    """Collapse a multi-line/oversized error into a single safe DB string.

    Stack traces and absolute paths must never reach the database; this keeps
    only the first line, truncated.

    Args:
        message: Raw exception text.
        limit: Maximum length to retain.

    Returns:
        A single-line, length-capped string.
    """
    first_line = (message or "").strip().splitlines()[0] if message else ""
    return first_line[:limit]

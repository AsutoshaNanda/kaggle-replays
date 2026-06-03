"""Safe filesystem operations: path-traversal guards, ZIP creation, streaming.

Every server-side path that incorporates user-controlled input is built through
:func:`safe_output_path`, which refuses any candidate that resolves outside its
base directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import AsyncIterator

import aiofiles


def safe_output_path(base_dir: Path, user_id: int, job_uuid: str) -> Path:
    """Build ``base_dir/user_id/job_uuid`` and verify it cannot escape ``base_dir``.

    Args:
        base_dir: The trusted base directory.
        user_id: Owning user's numeric ID.
        job_uuid: The job's UUID (path component).

    Returns:
        The resolved, validated candidate path.

    Raises:
        ValueError: If the resolved path escapes ``base_dir`` (traversal attempt).
    """
    base = base_dir.resolve()
    candidate = (base / str(user_id) / job_uuid).resolve()
    if not str(candidate).startswith(str(base)):
        raise ValueError(f"Path traversal attempt detected: {candidate}")
    return candidate


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) if missing; return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_zip(source_dir: Path, archive_base: Path) -> Path:
    """Create ``{archive_base}.zip`` from ``source_dir``; return the ZIP path.

    Args:
        source_dir: Directory whose contents are archived.
        archive_base: Target path *without* the ``.zip`` suffix.

    Returns:
        Path to the created ``.zip`` file.
    """
    archive = shutil.make_archive(str(archive_base), "zip", root_dir=str(source_dir))
    return Path(archive)


def delete_path(path: Path) -> None:
    """Best-effort recursive delete of a file or directory (ignores missing)."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        try:
            path.unlink()
        except OSError:
            pass


async def stream_file(path: Path, chunk_size: int = 64 * 1024) -> AsyncIterator[bytes]:
    """Yield a file's bytes in chunks for a ``StreamingResponse``.

    The file is never loaded fully into memory.

    Args:
        path: File to stream.
        chunk_size: Bytes per chunk.

    Yields:
        Successive byte chunks until EOF.
    """
    async with aiofiles.open(path, "rb") as handle:
        while True:
            chunk = await handle.read(chunk_size)
            if not chunk:
                break
            yield chunk

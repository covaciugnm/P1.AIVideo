"""File-storage helpers for the Phase 4A-2 upload endpoints.

The endpoints (in ``app/api/uploads.py``) call into these helpers to:

- Resolve the configured upload root (env-driven so tests can override).
- Create unique, safe filenames (uuid4-derived; never echoes the
  operator's original filename so an attacker can't inject a path like
  ``../../etc/passwd``).
- Stream the request body to disk in fixed-size chunks, enforcing a
  hard size cap so a maliciously large upload can't OOM the server.
- Compute a SHA-256 of the saved file once it's written.

No binary leaves these helpers via return value — they write to disk
and return path / size / hash metadata only.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile


_CHUNK_SIZE = 64 * 1024


def get_upload_root(env_name: str, default: str) -> Path:
    """Read an env-driven upload root, resolve to absolute, and ensure
    the directory exists.

    Reads on every call so tests can monkeypatch.setenv between
    requests without re-bootstrapping the app.
    """
    raw = os.environ.get(env_name, default)
    root = Path(raw).resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_unique_filename(extension: str) -> str:
    """Return a uuid4-derived filename with the given extension.

    The extension MUST start with a dot and contain only safe ASCII
    characters; we don't sanitize the operator's filename — we ignore it.
    """
    ext = extension.lower()
    if not ext.startswith("."):
        ext = "." + ext
    # Defensive: refuse any character that isn't [a-z0-9.]
    if any(c not in "abcdefghijklmnopqrstuvwxyz0123456789." for c in ext):
        raise ValueError(f"unsafe extension: {extension!r}")
    return f"{uuid.uuid4().hex}{ext}"


async def save_streaming_upload(
    file: UploadFile, dest: Path, *, max_size: int
) -> int:
    """Stream a multipart upload to ``dest``, enforcing ``max_size``.

    Cleans up partial files on size-cap violation. Returns the total
    number of bytes written on success. Raises ``HTTPException(413)`` if
    the file exceeds the cap.
    """
    total = 0
    try:
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size:
                    # Stop early, free the partial file.
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"upload exceeds max size of {max_size} bytes",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception:
        # Any other failure: scrub the partial file before bubbling up.
        dest.unlink(missing_ok=True)
        raise
    return total


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()

"""Path safety helpers — shared by the API and the voice handler.

Rules for accepting an operator-supplied local audio file path:

1. Path must be non-empty.
2. Path must be absolute (no relative paths).
3. Path components must not include ``..`` (no traversal).
4. After ``Path.resolve(strict=False)``, the path must be under one of the
   directories listed in ``$PROVIDED_AUDIO_ALLOWED_ROOTS`` (comma-separated).
5. Suffix must be ``.wav`` (case-insensitive).

File existence is intentionally NOT checked here: schemas validate
structural correctness without touching the filesystem. Existence checks
are the voice handler's job at execution time.

The allowed-roots env var is read on every call so tests can override it
with ``monkeypatch.setenv`` between requests without rebuilding the app.
"""
from __future__ import annotations

import os
from pathlib import Path


_DEFAULT_ROOTS = (
    "/workspace/assets/input/audio,"
    "/storage/inputs/audio,"
    "/app/assets/input/audio"
)


def get_allowed_audio_roots() -> list[str]:
    """Return the configured allowed-roots list. Strips empties + whitespace."""
    raw = os.environ.get("PROVIDED_AUDIO_ALLOWED_ROOTS", _DEFAULT_ROOTS)
    return [r.strip() for r in raw.split(",") if r.strip()]


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_local_audio_path(path: str) -> Path:
    """Verify ``path`` is a safe absolute ``.wav`` under an allowed root.

    Returns the normalized ``Path`` on success.

    Raises ``ValueError`` (the type Pydantic field/model validators expect)
    on any rejection. The message is human-readable and intentionally
    refers to the operator's input path verbatim so an actionable 422
    response can be produced.
    """
    if not path:
        raise ValueError("audio_ref.path must not be empty")

    raw = Path(path)

    if any(part == ".." for part in raw.parts):
        raise ValueError(f"audio_ref.path contains path traversal: {path!r}")

    if not raw.is_absolute():
        raise ValueError(f"audio_ref.path must be absolute: {path!r}")

    if raw.suffix.lower() != ".wav":
        raise ValueError(
            f"audio_ref.path must end in .wav (case-insensitive): {path!r}"
        )

    # Normalize without requiring the file to exist; this collapses any
    # remaining `.` segments and resolves symlinks where possible.
    resolved = raw.resolve(strict=False)

    allowed_roots = [Path(r).resolve(strict=False) for r in get_allowed_audio_roots()]
    if not allowed_roots:
        raise ValueError(
            "audio_ref.path rejected: PROVIDED_AUDIO_ALLOWED_ROOTS is unset"
        )

    if not any(_is_under(resolved, root) for root in allowed_roots):
        raise ValueError(
            f"audio_ref.path is outside the configured allowed roots: {path!r}"
        )

    return resolved

"""Path safety helpers — shared by the API and the voice / face handlers.

Rules for accepting an operator-supplied local file path:

1. Path must be non-empty.
2. Path must be absolute (no relative paths).
3. Path components must not include ``..`` (no traversal).
4. After ``Path.resolve(strict=False)``, the path must be under one of
   the directories listed in the kind-specific allowed-roots env var
   (``$PROVIDED_AUDIO_ALLOWED_ROOTS`` or ``$PROVIDED_IMAGE_ALLOWED_ROOTS``).
5. Suffix must be in the kind-specific allowlist (``.wav`` for audio;
   ``.png`` / ``.jpg`` / ``.jpeg`` / ``.webp`` for images, case-insensitive).

File existence is intentionally NOT checked here: schemas validate
structural correctness without touching the filesystem. Existence checks
are the handler's job at execution time.

Allowed-roots env vars are read on every call so tests can override them
with ``monkeypatch.setenv`` between requests without rebuilding the app.
"""
from __future__ import annotations

import os
from pathlib import Path


_DEFAULT_AUDIO_ROOTS = (
    "/workspace/assets/input/audio,"
    "/storage/inputs/audio,"
    "/app/assets/input/audio"
)
_DEFAULT_IMAGE_ROOTS = (
    "/workspace/assets/input/images,"
    "/storage/inputs/images,"
    "/app/assets/input/images"
)


def _split_roots(raw: str) -> list[str]:
    return [r.strip() for r in raw.split(",") if r.strip()]


def get_allowed_audio_roots() -> list[str]:
    return _split_roots(os.environ.get("PROVIDED_AUDIO_ALLOWED_ROOTS", _DEFAULT_AUDIO_ROOTS))


def get_allowed_image_roots() -> list[str]:
    return _split_roots(os.environ.get("PROVIDED_IMAGE_ALLOWED_ROOTS", _DEFAULT_IMAGE_ROOTS))


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_local_path(
    path: str,
    *,
    allowed_roots: list[str],
    allowed_extensions: set[str],
    field_name: str,
) -> Path:
    """Shared path-safety validator. See module docstring for rules."""
    if not path:
        raise ValueError(f"{field_name} must not be empty")

    raw = Path(path)

    if any(part == ".." for part in raw.parts):
        raise ValueError(f"{field_name} contains path traversal: {path!r}")

    if not raw.is_absolute():
        raise ValueError(f"{field_name} must be absolute: {path!r}")

    suffix = raw.suffix.lower()
    if suffix not in allowed_extensions:
        pretty = ", ".join(sorted(allowed_extensions))
        raise ValueError(
            f"{field_name} must have one of these extensions ({pretty}): {path!r}"
        )

    resolved = raw.resolve(strict=False)

    if not allowed_roots:
        env_var = (
            "PROVIDED_AUDIO_ALLOWED_ROOTS"
            if field_name.startswith("audio_ref")
            else "PROVIDED_IMAGE_ALLOWED_ROOTS"
        )
        raise ValueError(f"{field_name} rejected: {env_var} is unset")

    resolved_roots = [Path(r).resolve(strict=False) for r in allowed_roots]
    if not any(_is_under(resolved, root) for root in resolved_roots):
        raise ValueError(
            f"{field_name} is outside the configured allowed roots: {path!r}"
        )

    return resolved


def validate_local_audio_path(path: str) -> Path:
    """Verify ``path`` is a safe absolute ``.wav`` under an allowed audio root."""
    return _validate_local_path(
        path,
        allowed_roots=get_allowed_audio_roots(),
        allowed_extensions={".wav"},
        field_name="audio_ref.path",
    )


def validate_local_image_path(path: str) -> Path:
    """Verify ``path`` is a safe absolute image file under an allowed image root."""
    return _validate_local_path(
        path,
        allowed_roots=get_allowed_image_roots(),
        allowed_extensions={".png", ".jpg", ".jpeg", ".webp"},
        field_name="image_ref.path",
    )

"""Phase 11A — language catalog (config-backed registry).

Single source of truth for which UI / video / subtitle languages the
backend advertises. DB rows that store a language code (e.g.
``Job.video_language``) validate against this list; the
``GET /api/v1/config/languages`` endpoint serves it to the frontend.

Adding a new language is a one-line edit here — no migration required.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_UI_LANGUAGE: str = "ro"
DEFAULT_VIDEO_LANGUAGE: str = "ro"
DEFAULT_SUBTITLE_FORMAT: str = "srt"
SUPPORTED_SUBTITLE_FORMATS: tuple[str, ...] = ("srt", "vtt")


@dataclass(frozen=True)
class LanguageInfo:
    code: str
    label_native: str
    label_english: str
    enabled: bool = True
    rtl: bool = False


# Registry order is the order rendered in the UI dropdowns. Add new
# languages by appending here. Keep ``ro`` first so the default UI is
# Romanian on a fresh install.
LANGUAGES: tuple[LanguageInfo, ...] = (
    LanguageInfo(code="ro", label_native="Română", label_english="Romanian"),
    LanguageInfo(code="en", label_native="English", label_english="English"),
    # Examples of how to add more later (commented out):
    # LanguageInfo(code="fr", label_native="Français", label_english="French"),
    # LanguageInfo(code="de", label_native="Deutsch", label_english="German"),
)


def language_codes() -> tuple[str, ...]:
    return tuple(lang.code for lang in LANGUAGES if lang.enabled)


def is_supported_language(code: str | None) -> bool:
    if not code:
        return False
    return code in language_codes()


def is_supported_subtitle_format(fmt: str | None) -> bool:
    if not fmt:
        return False
    return fmt in SUPPORTED_SUBTITLE_FORMATS


def normalize_language(code: str | None, *, fallback: str = DEFAULT_VIDEO_LANGUAGE) -> str:
    """Return ``code`` if supported, otherwise ``fallback`` (ro by default).

    Used by API handlers that accept an optional language input and need
    to land a non-null value into a DB row.
    """
    if is_supported_language(code):
        return code  # type: ignore[return-value]
    return fallback


def catalog_payload() -> dict:
    """Shape returned by ``GET /api/v1/config/languages``."""
    return {
        "default_ui_language": DEFAULT_UI_LANGUAGE,
        "default_video_language": DEFAULT_VIDEO_LANGUAGE,
        "available_languages": [
            {
                "code": lang.code,
                "label_native": lang.label_native,
                "label_english": lang.label_english,
                "enabled": lang.enabled,
                "rtl": lang.rtl,
            }
            for lang in LANGUAGES
        ],
        "subtitle_defaults": {
            "enabled": False,
            "default_language": DEFAULT_VIDEO_LANGUAGE,
            "supported_formats": list(SUPPORTED_SUBTITLE_FORMATS),
            "burn_in_supported": False,  # Phase 11A: sidecar artifacts only.
        },
    }

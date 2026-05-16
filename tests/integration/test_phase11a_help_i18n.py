"""Phase 11A (re-do) — Help corpus must exist in both ro and en under
``frontend/lib/help/dictionaries/``. 30 required topic IDs in both files,
none empty.
"""
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HELP_DIR = REPO_ROOT / "frontend" / "lib" / "help" / "dictionaries"
HELP_EN = HELP_DIR / "en.ts"
HELP_RO = HELP_DIR / "ro.ts"


REQUIRED_TOPIC_IDS = {
    "dashboard",
    "jobs-list",
    "create-job",
    "provider-selection",
    "script-generation",
    "tts-generation",
    "f5tts-ro",
    "piper",
    "ollama",
    "sadtalker-video",
    "subtitles",
    "video-language",
    "uploads",
    "audio-upload",
    "image-upload",
    "job-detail",
    "artifacts",
    "real-vs-metadata",
    "qc-report",
    "final-export",
    "recovery-controls",
    "settings",
    "docker-ports",
    "provider-diagnostics",
    "logs",
    "custom-providers",
    "errors-glossary",
    "gpu-runtime",
    "model-assets",
    "demo-jobs",
    "localization",
}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _extract_topic_ids(src: str) -> set[str]:
    return set(re.findall(r"id:\s*\"([a-z0-9\-]+)\"", src))


def _extract_titles(src: str) -> dict[str, str]:
    """Pair every ``id: "..."`` with the title that follows it in the
    same topic literal."""
    pairs: dict[str, str] = {}
    for m in re.finditer(
        r"id:\s*\"([a-z0-9\-]+)\",\s*\n\s*section:\s*\"[^\"]*\",\s*\n\s*title:\s*\"([^\"]+)\"",
        src,
    ):
        pairs[m.group(1)] = m.group(2)
    return pairs


# ---------- files exist ----------


def test_help_dictionary_files_exist():
    assert HELP_EN.is_file(), f"missing: {HELP_EN.relative_to(REPO_ROOT)}"
    assert HELP_RO.is_file(), f"missing: {HELP_RO.relative_to(REPO_ROOT)}"


# ---------- 30 required topics in both ----------


def test_required_topics_in_en():
    ids = _extract_topic_ids(_read(HELP_EN))
    missing = REQUIRED_TOPIC_IDS - ids
    assert not missing, f"EN help corpus missing topic ids: {sorted(missing)}"


def test_required_topics_in_ro():
    ids = _extract_topic_ids(_read(HELP_RO))
    missing = REQUIRED_TOPIC_IDS - ids
    assert not missing, f"RO help corpus missing topic ids: {sorted(missing)}"


def test_en_and_ro_have_same_topic_ids():
    en_ids = _extract_topic_ids(_read(HELP_EN))
    ro_ids = _extract_topic_ids(_read(HELP_RO))
    only_en = en_ids - ro_ids
    only_ro = ro_ids - en_ids
    assert not only_en, f"Topic ids in EN missing from RO: {sorted(only_en)}"
    assert not only_ro, f"Topic ids in RO missing from EN: {sorted(only_ro)}"


# ---------- titles non-empty + different ----------


def test_titles_are_non_empty():
    for path in (HELP_EN, HELP_RO):
        titles = _extract_titles(_read(path))
        empty = [k for k, v in titles.items() if not v.strip()]
        assert not empty, f"{path.name}: empty titles for {empty}"


def test_ro_titles_are_translated():
    """At least 20 RO titles must differ from their EN counterparts."""
    en = _extract_titles(_read(HELP_EN))
    ro = _extract_titles(_read(HELP_RO))
    shared = set(en) & set(ro)
    diffs = sum(1 for k in shared if en[k] != ro[k])
    assert diffs >= 20, (
        f"Only {diffs} RO titles differ from EN — looks like a clone. "
        "Translate the help topics into Romanian."
    )


# ---------- provider tokens present in both ----------


def test_required_provider_tokens_in_en():
    src = _read(HELP_EN)
    for token in ("Ollama", "Piper", "F5TTS", "SadTalker", "ffmpeg", "GFPGAN"):
        assert token in src, f"EN help missing provider token: {token}"


def test_required_provider_tokens_in_ro():
    src = _read(HELP_RO)
    for token in ("Ollama", "Piper", "F5TTS", "SadTalker", "ffmpeg", "GFPGAN"):
        assert token in src, f"RO help missing provider token: {token}"


# ---------- error glossary topic exists ----------


def test_error_glossary_topic_lists_codes():
    for path in (HELP_EN, HELP_RO):
        src = _read(path)
        for code in (
            "script_provider_disabled",
            "tts_runtime_missing",
            "video_assets_missing",
        ):
            assert code in src, f"{path.name} missing error code in glossary: {code}"


# ---------- HelpOverlay actually consumes the dictionaries ----------


def test_help_overlay_uses_localized_corpus():
    overlay = (
        REPO_ROOT / "frontend" / "components" / "HelpOverlay.tsx"
    ).read_text(encoding="utf-8")
    assert "getLocalizedHelpCorpus" in overlay, (
        "HelpOverlay must call getLocalizedHelpCorpus(language) so help "
        "switches with the UI language."
    )


def test_help_hint_uses_language():
    hint = (
        REPO_ROOT / "frontend" / "components" / "HelpHint.tsx"
    ).read_text(encoding="utf-8")
    assert "useLanguage" in hint, (
        "HelpHint must read the current language so its tooltip is "
        "translated alongside the rest of the UI."
    )

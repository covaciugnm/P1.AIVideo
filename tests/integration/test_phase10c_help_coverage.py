"""Phase 10C — Help coverage. Updated in Phase 11A (re-do) to read from
the new bilingual help dictionaries at
``frontend/lib/help/dictionaries/{en,ro}.ts``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HELP_EN = REPO_ROOT / "frontend" / "lib" / "help" / "dictionaries" / "en.ts"
HELP_RO = REPO_ROOT / "frontend" / "lib" / "help" / "dictionaries" / "ro.ts"


REQUIRED_TOPIC_IDS = (
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
)

REQUIRED_PROVIDER_TOKENS = (
    "Ollama",
    "Piper",
    "F5TTS",
    "SadTalker",
    "ffmpeg",
    "GFPGAN",
)

REQUIRED_ERROR_CODES = (
    "script_provider_disabled",
    "script_model_missing",
    "tts_runtime_missing",
    "tts_assets_missing",
    "video_assets_missing",
    "video_gpu_missing",
    "provider_not_implemented",
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _topic_ids(src: str) -> set[str]:
    return set(re.findall(r"id:\s*\"([a-z0-9\-]+)\"", src))


def test_help_dictionary_files_exist():
    assert HELP_EN.is_file()
    assert HELP_RO.is_file()


def test_required_topics_present_in_both_languages():
    en_ids = _topic_ids(_read(HELP_EN))
    ro_ids = _topic_ids(_read(HELP_RO))
    for tid in REQUIRED_TOPIC_IDS:
        assert tid in en_ids, f"EN help missing topic: {tid}"
        assert tid in ro_ids, f"RO help missing topic: {tid}"


def test_required_provider_tokens_in_both_languages():
    en = _read(HELP_EN)
    ro = _read(HELP_RO)
    for tok in REQUIRED_PROVIDER_TOKENS:
        assert tok in en, f"EN missing provider token: {tok}"
        assert tok in ro, f"RO missing provider token: {tok}"


def test_required_error_codes_documented_in_glossary():
    en = _read(HELP_EN)
    ro = _read(HELP_RO)
    for code in REQUIRED_ERROR_CODES:
        assert code in en, f"EN error glossary missing: {code}"
        assert code in ro, f"RO error glossary missing: {code}"


@pytest.mark.parametrize("topic_id", REQUIRED_TOPIC_IDS)
def test_no_empty_topic_bodies(topic_id: str):
    """Each required topic in EN must have a non-empty body."""
    src = _read(HELP_EN)
    pattern = (
        r"id:\s*\""
        + re.escape(topic_id)
        + r"\"[\s\S]*?body:\s*\[(?P<body>[\s\S]*?)\][\s\S]*?(related:|\},\s*\n\s*[a-z\-]+:\s*\{)"
    )
    m = re.search(pattern, src)
    assert m is not None, f"Could not find body for topic={topic_id}"
    body = re.sub(r"\s+", "", m.group("body"))
    assert body, f"Empty body for topic={topic_id}"


def test_contribution_rules_doc_exists():
    rules = REPO_ROOT / "docs" / "runbooks" / "contribution-rules.md"
    assert rules.is_file(), f"missing {rules}"
    body = rules.read_text(encoding="utf-8")
    assert "Help & documentation maintenance rule" in body


def test_readme_links_to_contribution_rules():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Help & documentation maintenance rule" in readme
    assert "contribution-rules.md" in readme

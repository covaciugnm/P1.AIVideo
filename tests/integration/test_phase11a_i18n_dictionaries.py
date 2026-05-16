"""Phase 11A (re-do) — UI translation dictionaries.

Strict invariants:
- ``frontend/lib/i18n/dictionaries/en.ts`` exists.
- ``frontend/lib/i18n/dictionaries/ro.ts`` exists.
- Both files declare the same leaf-key set (no missing translations).
- No empty string translations.
- Every required UI key is present in both files.
- Error glossary keys are present in both files.
"""
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
UI_DIR = REPO_ROOT / "frontend" / "lib" / "i18n" / "dictionaries"
UI_EN = UI_DIR / "en.ts"
UI_RO = UI_DIR / "ro.ts"


# Required leaf keys. The dictionary type also enforces parity at TS
# compile time; this list captures the operator-facing minimum.
REQUIRED_UI_KEYS = {
    # nav
    "dashboard",
    "jobs",
    "newJob",
    "uploads",
    "settings",
    "help",
    # common
    "save",
    "cancel",
    "delete",
    "edit",
    "view",
    "retry",
    "refresh",
    "reset",
    "copy",
    "upload",
    "download",
    "test",
    "status",
    "provider",
    "language",
    "subtitles",
    "error",
    "loading",
    "noData",
    "close",
    "open",
    "back",
    "forward",
    "search",
    "available",
    "notConfigured",
    "notImplemented",
    "runtimeMissing",
    "assetsMissing",
    "preview",
    # createJob
    "sectionBrief",
    "briefLabel",
    "targetDuration",
    "sectionVoice",
    "scriptText",
    "sectionProviders",
    "scriptProvider",
    "ttsProvider",
    "videoProvider",
    "audioProcessor",
    "imageProcessor",
    "sectionFace",
    "useProvidedImage",
    "sectionLanguage",
    "videoLanguage",
    "enableSubtitles",
    "subtitleLanguages",
    "subtitleFormat",
    "burnSubtitles",
    "burnNotImplemented",
    "sectionCompliance",
    "syntheticConfirm",
    "consentConfirm",
    "generateScript",
    "generateAudio",
    "listen",
    "uploadAudio",
    "uploadImage",
    "submit",
    # uploads
    "textUpload",
    "audioUpload",
    "imageUpload",
    "recentUploads",
    "acceptedFormats",
    "maxFileSize",
    "uploadSuccessful",
    "uploadFailed",
    # settings
    "backendUrl",
    "testBackend",
    "dockerPorts",
    "pollingInterval",
    "autoPolling",
    "providerDefaults",
    "customProviders",
    "interfaceLanguage",
    "defaultVideoLanguage",
    "resetDefaults",
    # jobDetail
    "overview",
    "timeline",
    "complianceEvents",
    "qcReport",
    "finalExport",
    "recoveryControls",
    "cancelJob",
    "retryJob",
    "metadataOnly",
    "realMedia",
    "subtitlesOn",
    "subtitlesOff",
    "burnInStatus",
    # providers
    "testProvider",
    "requiresGpu",
    "requiresNetwork",
    "requiresModelFiles",
    # logs
    "exportJson",
    "exportTxt",
    "clearLogs",
    "sessionLocal",
    # help
    "searchPlaceholder",
    "related",
}

REQUIRED_ERROR_CODES = {
    "script_provider_disabled",
    "script_model_missing",
    "script_provider_unreachable",
    "script_generation_failed",
    "tts_runtime_missing",
    "tts_assets_missing",
    "tts_generation_failed",
    "tts_provider_not_configured",
    "tts_provider_not_implemented",
    "video_assets_missing",
    "video_gpu_missing",
    "video_runtime_missing",
    "video_provider_not_configured",
    "video_provider_not_implemented",
    "provider_not_implemented",
    "provider_not_configured",
    "artifact_not_found",
    "upload_failed",
    "validation_error",
}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _extract_leaf_keys(src: str) -> set[str]:
    """Capture every ``<key>: "<value>"`` declaration. Matches the
    shallow-namespace structure we use (no nested escaping)."""
    return set(re.findall(r"\n\s+([a-zA-Z_][a-zA-Z0-9_]*):\s*\"", src))


def _extract_kv_pairs(src: str) -> dict[str, str]:
    """Return ``{key: value}`` for every shallow string declaration."""
    pairs: dict[str, str] = {}
    for m in re.finditer(
        r"\n\s+([a-zA-Z_][a-zA-Z0-9_]*):\s*\"((?:[^\"\\]|\\.)*)\"",
        src,
    ):
        pairs[m.group(1)] = m.group(2)
    return pairs


# ---------- file existence ----------


def test_ui_dictionary_files_exist():
    assert UI_EN.is_file(), f"missing: {UI_EN.relative_to(REPO_ROOT)}"
    assert UI_RO.is_file(), f"missing: {UI_RO.relative_to(REPO_ROOT)}"


# ---------- key parity ----------


def test_en_and_ro_dictionaries_have_same_keys():
    en_keys = _extract_leaf_keys(_read(UI_EN))
    ro_keys = _extract_leaf_keys(_read(UI_RO))
    only_en = en_keys - ro_keys
    only_ro = ro_keys - en_keys
    assert not only_en, f"Keys present in EN but missing from RO: {sorted(only_en)}"
    assert not only_ro, f"Keys present in RO but missing from EN: {sorted(only_ro)}"


# ---------- required UI keys ----------


def test_required_ui_keys_present_in_en():
    keys = _extract_leaf_keys(_read(UI_EN))
    missing = REQUIRED_UI_KEYS - keys
    assert not missing, f"EN dictionary missing required keys: {sorted(missing)}"


def test_required_ui_keys_present_in_ro():
    keys = _extract_leaf_keys(_read(UI_RO))
    missing = REQUIRED_UI_KEYS - keys
    assert not missing, f"RO dictionary missing required keys: {sorted(missing)}"


# ---------- error glossary ----------


def test_required_error_codes_in_both_dictionaries():
    en_keys = _extract_leaf_keys(_read(UI_EN))
    ro_keys = _extract_leaf_keys(_read(UI_RO))
    missing_en = REQUIRED_ERROR_CODES - en_keys
    missing_ro = REQUIRED_ERROR_CODES - ro_keys
    assert not missing_en, f"EN missing error codes: {sorted(missing_en)}"
    assert not missing_ro, f"RO missing error codes: {sorted(missing_ro)}"


# ---------- no empty translations ----------


def test_no_empty_strings_in_ro():
    pairs = _extract_kv_pairs(_read(UI_RO))
    empties = [k for k, v in pairs.items() if not v.strip()]
    assert not empties, f"RO dictionary has empty string values: {empties}"


def test_no_empty_strings_in_en():
    pairs = _extract_kv_pairs(_read(UI_EN))
    empties = [k for k, v in pairs.items() if not v.strip()]
    assert not empties, f"EN dictionary has empty string values: {empties}"


# ---------- RO is actually translated (not just a clone) ----------


def test_ro_is_not_a_clone_of_en():
    """Spot-check: at least 20 leaf values must differ between EN and RO.
    Romanian text is grammatically distinct enough that a real translation
    has nearly zero overlap. A copy-paste of EN gets caught here."""
    en = _extract_kv_pairs(_read(UI_EN))
    ro = _extract_kv_pairs(_read(UI_RO))
    shared = set(en.keys()) & set(ro.keys())
    diffs = sum(1 for k in shared if en[k] != ro[k])
    assert diffs >= 20, (
        f"Only {diffs} keys differ between EN and RO — looks like a clone, not a "
        "translation. Translate the missing values."
    )


# ---------- Phase 11A-FIX: required sections + new key buckets ----------

# Top-level dictionary sections that MUST exist in both files. Captures
# the contract the formatters helper + UI components depend on.
REQUIRED_SECTIONS: tuple[str, ...] = (
    "common",
    "nav",
    "dashboard",
    "jobs",
    "jobDetail",
    "createJob",
    "uploads",
    "settings",
    "providers",
    "customProviders",
    "logs",
    "help",
    "statuses",
    "stages",
    "artifactTypes",
    "voiceModes",
    "faceModes",
    "providerStatuses",
    "runtime",
    "errors",
    "validation",
    "time",
)

# Required leaf keys inside specific sections. Matched as
# ``<section>.<leaf>`` once the test has located the section opener.
PHASE_11A_FIX_REQUIRED_KEYS: tuple[tuple[str, str], ...] = (
    ("statuses", "pending_compliance"),
    ("statuses", "rejected"),
    ("statuses", "failed"),
    ("statuses", "published"),
    ("statuses", "running"),
    ("statuses", "succeeded"),
    ("stages", "policy_gate"),
    ("stages", "scriptwriter"),
    ("stages", "voice"),
    ("stages", "lipsync"),
    ("stages", "publisher"),
    ("artifactTypes", "script"),
    ("artifactTypes", "audio"),
    ("artifactTypes", "image"),
    ("artifactTypes", "video"),
    ("artifactTypes", "final_export"),
    ("voiceModes", "tts"),
    ("voiceModes", "provided_audio"),
    ("faceModes", "provided_image"),
    ("providerStatuses", "available"),
    ("providerStatuses", "not_configured"),
    ("validation", "syntheticPersonRequired"),
    ("validation", "consentRequired"),
    ("validation", "scriptTextRequiredForTts"),
    ("validation", "targetDurationRange"),
    ("validation", "extraForbiddenField"),
    ("time", "justNow"),
    ("time", "secondsAgo"),
    ("time", "minutesAgo"),
    ("time", "hoursAgo"),
    ("time", "daysAgo"),
)

# Typo keys reported by Gemini that must NOT appear as bare keys
# (``\n  curent: "..."``). The strings may still occur INSIDE values
# (e.g. ``"curentă"``) — that's fine; we only reject them when they
# show up as identifiers.
FORBIDDEN_TYPO_KEYS = ("curent", "uat")


def _has_section(src: str, section: str) -> bool:
    return re.search(rf"\n\s+{re.escape(section)}:\s*\{{", src) is not None


def _section_body(src: str, section: str) -> str | None:
    """Return the body of a top-level ``section: { ... }`` block by
    brace-matching from the opener. Returns ``None`` if not found."""
    opener = re.search(rf"\n  {re.escape(section)}:\s*\{{", src)
    if not opener:
        return None
    start = opener.end()
    depth = 1
    i = start
    while i < len(src) and depth > 0:
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return src[start : i - 1]


def _has_leaf_in_section(src: str, section: str, leaf: str) -> bool:
    body = _section_body(src, section)
    if body is None:
        return False
    return re.search(rf"\n\s+{re.escape(leaf)}:\s*[\"'`]", body) is not None


def test_required_sections_in_en():
    src = _read(UI_EN)
    missing = [s for s in REQUIRED_SECTIONS if not _has_section(src, s)]
    assert not missing, f"EN dictionary missing required sections: {missing}"


def test_required_sections_in_ro():
    src = _read(UI_RO)
    missing = [s for s in REQUIRED_SECTIONS if not _has_section(src, s)]
    assert not missing, f"RO dictionary missing required sections: {missing}"


def test_phase_11a_fix_keys_in_en():
    src = _read(UI_EN)
    missing = [
        f"{section}.{leaf}"
        for section, leaf in PHASE_11A_FIX_REQUIRED_KEYS
        if not _has_leaf_in_section(src, section, leaf)
    ]
    assert not missing, f"EN missing Phase 11A-FIX keys: {missing}"


def test_phase_11a_fix_keys_in_ro():
    src = _read(UI_RO)
    missing = [
        f"{section}.{leaf}"
        for section, leaf in PHASE_11A_FIX_REQUIRED_KEYS
        if not _has_leaf_in_section(src, section, leaf)
    ]
    assert not missing, f"RO missing Phase 11A-FIX keys: {missing}"


def test_no_typo_keys_in_dictionaries():
    """Bare keys like ``curent`` or ``uat`` are typos — the canonical
    forms are inside ``curentă`` / ``uitat`` / value strings. They must
    not appear as identifiers (``\n  curent: \"…\"``)."""
    for label, path in (("EN", UI_EN), ("RO", UI_RO)):
        src = _read(path)
        for typo in FORBIDDEN_TYPO_KEYS:
            pattern = rf"\n\s+{re.escape(typo)}:\s*[\"'`]"
            assert not re.search(pattern, src), (
                f"{label} dictionary declares a typo key {typo!r}"
            )


def test_no_identical_non_technical_pairs():
    """For every leaf that exists in both dictionaries, the RO value
    must differ from the EN value unless the leaf is on the
    technical allowlist (provider IDs, file formats, language tokens,
    ``MP4`` etc.). Catches accidentally-copy-pasted RO values that
    should have been translated.

    The allowlist is intentionally narrow: every entry on it must be
    a value the operator would expect to see verbatim in either
    language."""
    en = _extract_kv_pairs(_read(UI_EN))
    ro = _extract_kv_pairs(_read(UI_RO))
    # Values that are deliberately byte-identical EN/RO because they're
    # technical tokens (abbreviations / file formats / brand names /
    # loanwords like "Editor"/"Backend"/"Lip-sync").
    ALLOWED_IDENTICAL = {
        "TTS", "Audio", "Video", "OK", "info", "frontend", "backend",
        "api", "MP4", "SRT", "WebVTT", "Manifest", "Stub", "Real",
        "sidecar", "QC", "Backend",
        "Editor", "Lip-sync", "Local", "local", "external",
        "Export JSON", "Export TXT", "Test1",
        "Dim / Dur", "manifest",
        # Technical / format-spec strings that read identically in EN
        # and RO (units, deltas, file-extension labels).
        "Audio (WAV)", "audio {seconds}s", "Δ {delta}",
        "HTTP {status}: {detail}",
        # Placeholders / patterns. ``{n}`` and similar templates are
        # numbers / paths that read the same in both languages.
        "{count}", "{visible} / {total}", "{n} / {max}",
        "watermark {status}", "c2pa {status}",
    }
    suspects: list[tuple[str, str]] = []
    for k, v_en in en.items():
        if k not in ro:
            continue
        v_ro = ro[k]
        if v_en != v_ro:
            continue
        stripped = v_en.strip()
        if stripped in ALLOWED_IDENTICAL:
            continue
        # URL / placeholder / brace-template strings are safe to share.
        if stripped.startswith(("http://", "https://", "{")):
            continue
        # Single uppercase token (GET, POST, SRT, …).
        if stripped.isupper() and " " not in stripped:
            continue
        # Tokens ≤3 chars: typically abbreviations (OK, SRT, …) — too
        # short to translate meaningfully.
        if len(stripped) <= 3:
            continue
        suspects.append((k, v_en))
    assert not suspects, (
        "Non-technical leaves have identical EN/RO values (suspected "
        f"copy-paste): {suspects[:10]}"
    )

"""Phase 11A-FIX — static scan for hardcoded English UI strings.

Goal:
    Catch the exact Gemini-reported regressions so the bilingual UI
    cannot silently re-introduce English. Only the operator-visible
    strings are flagged; technical tokens (provider IDs, API paths,
    env-var names, file formats, log meta) are on the allowlist.

The scan is intentionally conservative — false negatives are OK as
long as the named regressions stay caught. It walks
``frontend/app/`` + ``frontend/components/``, reads every ``.tsx``
file, and asserts that none of the banned phrases appear outside of
comments / log messages / dictionary files.
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
SCAN_DIRS = [FRONTEND / "app", FRONTEND / "components"]
# These files legitimately contain English source text (they ARE the
# dictionary), or are not part of the visible UI.
EXCLUDE_PATHS = {
    FRONTEND / "lib" / "i18n" / "dictionaries" / "en.ts",
    FRONTEND / "lib" / "help" / "dictionaries" / "en.ts",
}


# Each (phrase, allowlist of file path suffixes where it's still
# allowed) pair. The Gemini audit specifically called these strings
# out; if the phrase reappears in a non-allowlisted file we fail.
BANNED_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Gemini-reported leaks.
    ("Generating script", ()),
    ("Fill in the brief first", ()),
    ("No compliance events", ()),
    ('aria-label="Progress"', ()),
    ('label={label ?? "Loading…"}', ()),
    ("Supported models (comma-separated)", ()),
    ("No custom providers yet", ()),
    ('"Exported ', ()),
    # humanize() fallback in visible UI — banned outside the formatters
    # helper (which uses it as a labelled fallback).
    ('humanize(progress.current_stage)', ()),
    ('humanize(job.voice_mode)', ()),
    ('humanize(job.face_mode)', ()),
    ('humanize(a.artifact_type)', ()),
    ('humanize(fit.fit_status)', ()),
    ('humanize(fit.recommendation)', ()),
    # formatRelative used to leak "s ago" / "m ago" — visible callers
    # must go through formatRelativeLocalized.
    ("formatRelative(job.updated_at)", ()),
    # Hardcoded English strings in older versions of the panels.
    ('Logs are local browser diagnostics', ()),
    ('Raw TCP — browser cannot test', ()),
    ('"Auto-linked to Backend host port', ()),
    ('"Checked indirectly via backend', ()),
    ('Job is in a terminal state. Polling stopped', ()),
)


def _iter_tsx() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*.tsx"):
            if path in EXCLUDE_PATHS:
                continue
            files.append(path)
    return files


@pytest.mark.parametrize("phrase,allow", BANNED_PHRASES)
def test_banned_phrase_absent(phrase: str, allow: tuple[str, ...]):
    """Every banned phrase from the Gemini audit must be gone."""
    offenders: list[str] = []
    for path in _iter_tsx():
        text = path.read_text(encoding="utf-8")
        if phrase not in text:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        # Allow if the file is explicitly whitelisted for this phrase.
        if any(rel.endswith(s) for s in allow):
            continue
        offenders.append(rel)
    assert not offenders, (
        f"Banned English phrase {phrase!r} still present in: {offenders}"
    )


def test_format_relative_only_called_via_localized_wrapper():
    """``formatRelative`` (the English-only legacy helper) must not
    appear in visible UI files anymore. The replacement is
    ``formatRelativeLocalized`` in ``frontend/lib/i18n/formatters.ts``.
    """
    import re

    raw_callers: list[str] = []
    # Match ``formatRelative(`` only when it's the actual identifier
    # (preceded by start-of-line / non-identifier char) and NOT followed
    # by ``Localized``.
    pattern = re.compile(r"(?<![A-Za-z_])formatRelative\(")
    for path in _iter_tsx():
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if pattern.search(line):
                raw_callers.append(
                    f"{path.relative_to(REPO_ROOT).as_posix()}:{line_no}"
                )
    assert not raw_callers, (
        "formatRelative is English-only; replace with formatRelativeLocalized:"
        f" {raw_callers}"
    )


def test_progress_aria_label_uses_translation():
    """ProgressBar's aria-label must go through ``t()``, not the raw
    English string."""
    src = (FRONTEND / "components" / "ProgressBar.tsx").read_text(encoding="utf-8")
    assert "aria-label={t(" in src, "ProgressBar must use t() for aria-label"
    assert 'aria-label="Progress"' not in src


def test_loading_state_uses_translation():
    """LoadingState's default label must go through ``t()``."""
    src = (FRONTEND / "components" / "LoadingState.tsx").read_text(encoding="utf-8")
    assert "useT" in src
    assert "t(\"common.loading\")" in src


def test_compliance_events_uses_translation():
    """ComplianceEvents empty-state message must come from the dictionary."""
    src = (FRONTEND / "components" / "ComplianceEvents.tsx").read_text(encoding="utf-8")
    assert "useT" in src
    assert "complianceList.empty" in src
    assert "No compliance events recorded yet." not in src


def test_custom_providers_uses_translation():
    """CustomProvidersSection must not contain the hardcoded form labels."""
    src = (
        FRONTEND / "components" / "CustomProvidersSection.tsx"
    ).read_text(encoding="utf-8")
    assert "customProviders.providerIdSlugSafe" in src
    assert "customProviders.supportedModelsCsv" in src
    assert "No custom providers yet." not in src
    assert "Supported models (comma-separated)" not in src


def test_format_module_humanize_not_used_in_visible_jsx():
    """The legacy ``humanize`` helper must not be IMPORTED by mainline
    visible components (Dashboard, Jobs list, ArtifactTable, StageTimeline,
    StatusBadge). Stray comments referencing the name are fine — we
    only flag actual imports / function calls."""
    import re

    visible = [
        FRONTEND / "components" / "StatusBadge.tsx",
        FRONTEND / "components" / "StageTimeline.tsx",
        FRONTEND / "components" / "ArtifactTable.tsx",
        FRONTEND / "components" / "ComplianceEvents.tsx",
    ]
    # Match ``humanize`` only as an imported identifier or a call.
    # Skip lines that are line comments — stray references in
    # explanatory comments are fine.
    import_pat = re.compile(r"^\s*import[^\n]*\bhumanize\b")
    call_pat = re.compile(r"\bhumanize\(")
    leaked: list[str] = []
    for path in visible:
        text = path.read_text(encoding="utf-8")
        offenders: list[str] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if import_pat.search(line) or call_pat.search(line):
                offenders.append(f"line {line_no}")
        if offenders:
            leaked.append(f"{path.relative_to(REPO_ROOT).as_posix()} ({', '.join(offenders)})")
    assert not leaked, (
        f"These components still import or call humanize() in visible UI: {leaked}"
    )

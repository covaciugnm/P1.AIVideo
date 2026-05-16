"""Phase 11B — UI static contract for the Edit job flow.

These tests are structural — they read source files and assert that
the operator-visible edit affordances exist. They don't spin up the
Next.js dev server.

What this phase pins:

- ``frontend/app/jobs/[jobId]/edit/page.tsx`` exists and wires the
  full provider_selection + language/subtitle editing surface.
- The Job Detail page exposes a link/button to the edit page.
- The Jobs List page exposes an edit link per row.
- ``frontend/lib/api.ts`` exports a typed ``updateJob`` plus the
  ``JobUpdateBody`` shape.
- The edit form imports useT() and uses Save / Cancel / Retry labels
  via the i18n dictionary (no hardcoded English buttons).
- The help corpus contains the three Phase 11B topics (edit-job,
  retry-job, failed-job-recovery) in BOTH languages.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
EDIT_PAGE = FRONTEND / "app" / "jobs" / "[jobId]" / "edit" / "page.tsx"
JOB_DETAIL_PAGE = FRONTEND / "app" / "jobs" / "[jobId]" / "page.tsx"
JOBS_LIST_PAGE = FRONTEND / "app" / "jobs" / "page.tsx"
API_TS = FRONTEND / "lib" / "api.ts"
TYPES_TS = FRONTEND / "lib" / "types.ts"
HELP_EN = FRONTEND / "lib" / "help" / "dictionaries" / "en.ts"
HELP_RO = FRONTEND / "lib" / "help" / "dictionaries" / "ro.ts"
DICT_EN = FRONTEND / "lib" / "i18n" / "dictionaries" / "en.ts"
DICT_RO = FRONTEND / "lib" / "i18n" / "dictionaries" / "ro.ts"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Edit page file exists.
# ---------------------------------------------------------------------------


def test_edit_page_exists():
    assert EDIT_PAGE.is_file(), f"missing: {EDIT_PAGE.relative_to(REPO_ROOT)}"
    src = _read(EDIT_PAGE)
    # Sanity: it's a client page that calls updateJob.
    assert '"use client"' in src
    assert "updateJob" in src


# ---------------------------------------------------------------------------
# 2. Job Detail has a link to the edit page.
# ---------------------------------------------------------------------------


def test_job_detail_links_to_edit_page():
    src = _read(JOB_DETAIL_PAGE)
    assert "/edit" in src, "job detail page must link to /jobs/{id}/edit"
    # Use a regex so we tolerate either template-literal or string form.
    assert re.search(r"/jobs/\$\{jobId\}/edit|/jobs/\${[^}]+}/edit", src), (
        "edit link must reference the dynamic jobId path"
    )
    # And it surfaces the canonical i18n label, not raw English.
    assert 'jobDetail.editJob' in src


# ---------------------------------------------------------------------------
# 3. Jobs List has an edit link per row.
# ---------------------------------------------------------------------------


def test_jobs_list_has_edit_link():
    src = _read(JOBS_LIST_PAGE)
    assert re.search(r"/jobs/\$\{[^}]+\}/edit", src), (
        "jobs list page must link to /jobs/{id}/edit"
    )
    # The visible label must come from the dictionary (common.edit), not a
    # hardcoded string.
    assert 'common.edit' in src


# ---------------------------------------------------------------------------
# 4. api.ts exposes updateJob and the JobUpdateBody type.
# ---------------------------------------------------------------------------


def test_api_client_exports_update_job():
    api = _read(API_TS)
    assert re.search(r"export\s+function\s+updateJob\b", api), (
        "api.ts must export updateJob"
    )
    # PATCH /api/v1/jobs/{id} via the typed body.
    assert "/api/v1/jobs/${jobId}" in api or '"/api/v1/jobs/" + jobId' in api
    assert '"PATCH"' in api

    types = _read(TYPES_TS)
    assert re.search(r"interface\s+JobUpdateBody\b", types), (
        "types.ts must declare JobUpdateBody"
    )
    # The body covers the Phase 11B editable surface.
    for key in (
        "brief",
        "target_duration_seconds",
        "provider_selection",
        "video_language",
        "subtitle_enabled",
    ):
        assert key in types


# ---------------------------------------------------------------------------
# 5. Edit UI references every provider_selection field.
# ---------------------------------------------------------------------------


def test_edit_page_references_provider_selection_fields():
    src = _read(EDIT_PAGE)
    required_keys = [
        "script_provider_id",
        "tts_provider_id",
        "video_provider_id",
        "audio_processor_id",
        "image_processor_id",
        "provider_selection",
    ]
    missing = [k for k in required_keys if k not in src]
    assert not missing, f"edit page missing provider-selection bindings: {missing}"


# ---------------------------------------------------------------------------
# 6. Edit UI uses i18n for Save / Cancel / Retry labels.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "common.cancel",
        "editJob.saveChanges",
        "editJob.saving",
        "editJob.retryAfterEdit",
        "editJob.failedToLoad",
        "editJob.updateRejected",
        "editJob.changesSaved",
    ],
)
def test_edit_page_uses_i18n_label(key):
    src = _read(EDIT_PAGE)
    # Allow either the t("…") direct call form or t(`…`).
    pattern = rf't\([\"`]{re.escape(key)}[\"`]\)'
    assert re.search(pattern, src), (
        f"edit page must surface label via t({key!r})"
    )
    # And the key must exist in both dictionaries so the t() call
    # actually resolves at runtime.
    section, leaf = key.split(".")
    for dict_path in (DICT_EN, DICT_RO):
        contents = _read(dict_path)
        section_pattern = rf"{section}:\s*\{{"
        assert re.search(section_pattern, contents), (
            f"{dict_path.name} missing section {section!r}"
        )
        leaf_pattern = rf"\n\s+{leaf}:\s*\""
        assert re.search(leaf_pattern, contents), (
            f"{dict_path.name} missing leaf {section}.{leaf}"
        )


# ---------------------------------------------------------------------------
# 7. Help corpus has the three Phase 11B topics in EN + RO.
# ---------------------------------------------------------------------------


PHASE_11B_HELP_TOPICS = ("edit-job", "retry-job", "failed-job-recovery")


@pytest.mark.parametrize("topic_id", PHASE_11B_HELP_TOPICS)
def test_help_topic_in_english(topic_id):
    src = _read(HELP_EN)
    assert re.search(rf'id:\s*"{re.escape(topic_id)}"', src), (
        f"missing {topic_id} in english help corpus"
    )


@pytest.mark.parametrize("topic_id", PHASE_11B_HELP_TOPICS)
def test_help_topic_in_romanian(topic_id):
    src = _read(HELP_RO)
    assert re.search(rf'id:\s*"{re.escape(topic_id)}"', src), (
        f"missing {topic_id} in romanian help corpus"
    )


def test_phase11b_help_topics_referenced_from_recovery_controls():
    """The Recovery controls help topic should cross-link to the
    Phase 11B topics so operators discovering the page find the new
    edit / retry recipes."""
    for dict_path in (HELP_EN, HELP_RO):
        src = _read(dict_path)
        # Find the recovery-controls topic body.
        block = re.search(
            r'id:\s*"recovery-controls".*?related:\s*\[([^\]]+)\]', src, re.S
        )
        assert block, f"recovery-controls topic not found in {dict_path.name}"
        related = block.group(1)
        for topic in PHASE_11B_HELP_TOPICS:
            assert f'"{topic}"' in related, (
                f"recovery-controls in {dict_path.name} should link to {topic}"
            )

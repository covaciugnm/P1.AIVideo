"""Phase 11E — UI static contract for the lipsync recovery flow.

Pins the front-end pieces Phase 11E ships:

1. EN+RO dictionaries declare ``errors.video_face_landmark_missing`` +
   ``errors.video_face_image_too_small`` so the operator-facing error
   bus can localise both error codes.
2. EN+RO dictionaries declare the ``videoRecovery.*`` section that
   ``VideoRecoveryHint`` consumes.
3. ``VideoRecoveryHint.tsx`` matches the canonical Phase 11E error
   codes and renders ``editJob.replaceFaceImage`` / retry actions.
4. Job Detail page imports + uses VideoRecoveryHint so the recovery
   card appears whenever the rejection_reason matches.
5. Edit Job page renders the image-replacement section (UploadCard
   kind="image" + the image preview) when the job is recoverable.
6. The SadTalker help topic now documents portrait requirements +
   categorised error codes in BOTH languages.
7. The operator-facing error message never starts with a raw Python
   ``TypeError`` — the dictionary mapping wins.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
DICT_EN = FRONTEND / "lib" / "i18n" / "dictionaries" / "en.ts"
DICT_RO = FRONTEND / "lib" / "i18n" / "dictionaries" / "ro.ts"
HELP_EN = FRONTEND / "lib" / "help" / "dictionaries" / "en.ts"
HELP_RO = FRONTEND / "lib" / "help" / "dictionaries" / "ro.ts"
RECOVERY_HINT = FRONTEND / "components" / "VideoRecoveryHint.tsx"
JOB_DETAIL = FRONTEND / "app" / "jobs" / "[jobId]" / "page.tsx"
EDIT_PAGE = FRONTEND / "app" / "jobs" / "[jobId]" / "edit" / "page.tsx"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------
# 1. errors.video_face_* keys present in both dictionaries.
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["video_face_landmark_missing", "video_face_image_too_small", "video_generation_failed"],
)
def test_error_keys_in_both_dictionaries(key):
    en = _read(DICT_EN)
    ro = _read(DICT_RO)
    pat = rf"\n\s+{re.escape(key)}:\s*\""
    assert re.search(pat, en), f"EN dictionary missing errors.{key}"
    assert re.search(pat, ro), f"RO dictionary missing errors.{key}"


# ---------------------------------------------------------------------
# 2. videoRecovery section keys.
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "leaf",
    [
        "faceLandmarkMissingTitle",
        "faceLandmarkMissingBody",
        "faceImageTooSmallTitle",
        "faceImageTooSmallBody",
        "uploadClearPortrait",
        "editAndReplaceImage",
        "retryAfterEdit",
        "portraitRequirements",
    ],
)
def test_video_recovery_section_in_both_dictionaries(leaf):
    en = _read(DICT_EN)
    ro = _read(DICT_RO)
    pat = rf"videoRecovery:\s*\{{[\s\S]*?\n\s+{re.escape(leaf)}:\s*\""
    assert re.search(pat, en), f"EN dictionary missing videoRecovery.{leaf}"
    assert re.search(pat, ro), f"RO dictionary missing videoRecovery.{leaf}"


# ---------------------------------------------------------------------
# 3. VideoRecoveryHint component pattern + actions.
# ---------------------------------------------------------------------


def test_video_recovery_hint_matches_known_codes():
    src = _read(RECOVERY_HINT)
    # The component must look for both Phase 11E error codes (string
    # match — the rejection_reason format is ``<code>: <message>``).
    assert "video_face_landmark_missing" in src
    assert "video_face_image_too_small" in src
    # And surface the localized title + body keys.
    assert "videoRecovery.faceLandmarkMissingTitle" in src
    assert "videoRecovery.faceLandmarkMissingBody" in src
    assert "videoRecovery.editAndReplaceImage" in src
    # The recovery card must not render the raw Python traceback as
    # the primary line — the body comes from the dictionary.
    assert "TypeError: exceptions must derive" not in src


# ---------------------------------------------------------------------
# 4. Job Detail page mounts VideoRecoveryHint.
# ---------------------------------------------------------------------


def test_job_detail_imports_video_recovery_hint():
    src = _read(JOB_DETAIL)
    assert "VideoRecoveryHint" in src, (
        "Job Detail must mount the VideoRecoveryHint card so SadTalker "
        "lipsync rejections show a clean recovery message to the operator"
    )
    # The hint must be passed the rejection_reason + canEdit + canRetry
    # signals so it can decide whether to render at all and what
    # actions to enable.
    assert "rejection_reason" in src
    assert "can_edit" in src
    assert "can_retry" in src


# ---------------------------------------------------------------------
# 5. Edit page surfaces image-replacement controls.
# ---------------------------------------------------------------------


def test_edit_page_renders_image_replacement_section():
    src = _read(EDIT_PAGE)
    # Phase 11E adds an UploadCard kind="image" that swaps the portrait
    # on a recoverable job.
    assert "<UploadCard" in src
    assert 'kind="image"' in src
    # The submit handler must forward the new artifact_id under the
    # canonical Phase 11E field name.
    assert "image_artifact_id" in src
    # Show the current image filename so the operator knows what
    # they're replacing.
    assert "editJob.currentImage" in src


# ---------------------------------------------------------------------
# 6. SadTalker help topic documents portrait + categorised codes.
# ---------------------------------------------------------------------


@pytest.mark.parametrize("help_file", [HELP_EN, HELP_RO])
def test_sadtalker_topic_documents_portrait_requirements(help_file):
    src = _read(help_file)
    # The topic body must mention the categorised codes the operator
    # will see in the recovery card.
    assert "video_face_landmark_missing" in src, (
        f"{help_file.name} sadtalker topic must mention video_face_landmark_missing"
    )
    assert "video_face_image_too_small" in src, (
        f"{help_file.name} sadtalker topic must mention video_face_image_too_small"
    )


# ---------------------------------------------------------------------
# 7. Operator-facing error message never leaks the raw TypeError.
# ---------------------------------------------------------------------


def test_dictionary_landmark_message_is_human():
    """The localized error message for video_face_landmark_missing
    must NOT just echo SadTalker's Python traceback — it has to be the
    front-facing-portrait instruction so the operator knows what to
    do."""
    for path in (DICT_EN, DICT_RO):
        src = _read(path)
        match = re.search(
            r'video_face_landmark_missing:\s*"([^"]+(?:\\.[^"]*)*)"', src
        )
        assert match, f"{path.name} missing video_face_landmark_missing value"
        msg = match.group(1).lower()
        # Must include a human action ("upload" / "încarcă") and NOT
        # the python type-error string.
        assert "upload" in msg or "încarcă" in msg
        assert "typeerror" not in msg
        assert "exceptions must derive" not in msg

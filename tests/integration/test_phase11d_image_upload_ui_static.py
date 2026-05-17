"""Phase 11D — UI static contract for image attachment.

Pins the audited operator flow:

1. CreateJobForm includes a Face/Image section with an image upload
   control (UploadCard kind="image").
2. CreateJobForm forwards ``image_artifact_id`` + face_mode in the
   from-inputs payload.
3. Edit Job page surfaces face_mode (read-only per the immutable-fields
   policy — image cannot be replaced post-creation, by design).
4. Job Detail page displays the image artifact via the ArtifactTable
   and the face_mode field.
5. EN+RO i18n dictionaries carry the face/image labels CreateJobForm
   uses.
6. Help corpora carry the talking-head input topic in both languages.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
CREATE_FORM = FRONTEND / "components" / "CreateJobForm.tsx"
UPLOAD_CARD = FRONTEND / "components" / "UploadCard.tsx"
JOB_DETAIL = FRONTEND / "app" / "jobs" / "[jobId]" / "page.tsx"
EDIT_PAGE = FRONTEND / "app" / "jobs" / "[jobId]" / "edit" / "page.tsx"
DICT_EN = FRONTEND / "lib" / "i18n" / "dictionaries" / "en.ts"
DICT_RO = FRONTEND / "lib" / "i18n" / "dictionaries" / "ro.ts"
HELP_EN = FRONTEND / "lib" / "help" / "dictionaries" / "en.ts"
HELP_RO = FRONTEND / "lib" / "help" / "dictionaries" / "ro.ts"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------
# 1. CreateJobForm has an image upload control + Face section.
# ---------------------------------------------------------------------


def test_create_job_form_renders_face_section_and_image_upload():
    src = _read(CREATE_FORM)
    # Section heading routes through i18n.
    assert "createJob.sectionFace" in src, (
        "CreateJobForm must surface the Face section title via the dictionary"
    )
    # The upload control is the shared UploadCard with kind="image".
    assert "<UploadCard" in src and "kind=\"image\"" in src, (
        "CreateJobForm must use <UploadCard kind=\"image\" ...> to "
        "upload portrait files"
    )
    # The form imports both UploadCard and the i18n hook.
    assert 'from "./UploadCard"' in src
    assert "useT" in src


def test_upload_card_accepts_image_extensions():
    src = _read(UPLOAD_CARD)
    # The card surface lives in the i18n dictionary; the actual ext
    # allowlist is passed in as a prop. We just confirm UploadCard
    # exposes that prop and renders an <input type="file" /> with the
    # accept attribute.
    assert 'acceptExtensions' in src
    assert 'type="file"' in src
    assert 'accept={accept}' in src


# ---------------------------------------------------------------------
# 2. Submit handler forwards image_artifact_id + face_mode.
# ---------------------------------------------------------------------


def test_create_job_form_forwards_image_artifact_id():
    src = _read(CREATE_FORM)
    # Payload construction must include image_artifact_id (the
    # canonical Phase 4A-2 / 11A name) — *not* face_artifact_id, *not*
    # input_image_artifact_id — so the backend contract is stable.
    assert "image_artifact_id" in src
    assert "face_mode" in src
    # The form also captures the consent + synthetic-person flags
    # required by JobFromInputsRequest.
    assert "image_consent_confirmed" in src
    assert "image_synthetic_person_confirmed" in src


# ---------------------------------------------------------------------
# 3. Edit page surfaces face_mode (read-only per immutable policy).
# ---------------------------------------------------------------------


def test_edit_page_surfaces_face_mode():
    src = _read(EDIT_PAGE)
    # face_mode is rendered in the read-only block; the schema makes it
    # immutable past pending_compliance.
    assert re.search(r"jobDetail\.faceMode", src), (
        "Edit page must display jobDetail.faceMode (read-only) so the "
        "operator knows the current face attachment"
    )
    # Read-only label heading must be present so the operator
    # understands they cannot edit it inline.
    assert "editJob.readOnly" in src


# ---------------------------------------------------------------------
# 4. Job Detail page shows face_mode + delegates image preview to the
#    ArtifactTable (the table renders a row per artifact_type=image).
# ---------------------------------------------------------------------


def test_job_detail_surfaces_face_mode_and_artifact_table():
    src = _read(JOB_DETAIL)
    assert "jobDetail.faceMode" in src, (
        "Job Detail must display the job's face_mode field"
    )
    assert "<ArtifactTable" in src, (
        "Job Detail must include ArtifactTable so image artifacts show"
    )


# ---------------------------------------------------------------------
# 5. i18n dictionary keys used by the face/image section.
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "section,leaf",
    [
        ("createJob", "sectionFace"),
        ("createJob", "useProvidedImage"),
        ("createJob", "providedImageTitle"),
        ("createJob", "imageConsent"),
        ("createJob", "imageSynthetic"),
        ("createJob", "uploadImage"),
        ("createJob", "missingImageRef"),
        ("jobDetail", "faceMode"),
        ("faceModes", "provided_image"),
        ("faceModes", "none"),
    ],
)
def test_required_face_image_keys_in_both_dictionaries(section, leaf):
    en = _read(DICT_EN)
    ro = _read(DICT_RO)
    # Each leaf must be declared inside its section in BOTH files.
    en_pat = rf"{section}:\s*\{{[\s\S]*?\n\s+{leaf}:\s*\""
    ro_pat = rf"{section}:\s*\{{[\s\S]*?\n\s+{leaf}:\s*\""
    assert re.search(en_pat, en), f"EN dictionary missing {section}.{leaf}"
    assert re.search(ro_pat, ro), f"RO dictionary missing {section}.{leaf}"


# ---------------------------------------------------------------------
# 6. Help corpora carry the face/image topics in both languages.
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "topic",
    [
        # Existing topic that already documents the talking-head input
        # contract end to end.
        "image-upload",
        # SadTalker topic is where the user looks when wondering why
        # their image-attached job didn't produce a video.
        "sadtalker-video",
        # Create-job + edit-job topics need to mention the image flow
        # in passing.
        "create-job",
        "edit-job",
    ],
)
def test_required_help_topics_in_both_languages(topic):
    en = _read(HELP_EN)
    ro = _read(HELP_RO)
    pat = rf'id:\s*"{re.escape(topic)}"'
    assert re.search(pat, en), f"EN help missing {topic}"
    assert re.search(pat, ro), f"RO help missing {topic}"

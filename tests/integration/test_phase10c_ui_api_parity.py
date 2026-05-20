"""Phase 10C — UI ↔ API parity static guard.

Reads the frontend source tree and asserts the parity matrix in
``docs/runbooks/ui-api-parity.md`` doesn't drift. The checks are
deliberately lightweight (regex / substring on file contents) so the
test stays fast and doesn't pull a browser / Node / TypeScript compiler.

If you remove or rename one of the items below, update **both** the
frontend AND ``docs/runbooks/ui-api-parity.md`` in the same commit.
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"


# Every page in the dashboard. Pages declared here must (a) exist on
# disk and (b) embed at least one <HelpHint /> or <HelpButton /> anchor
# so the operator has discoverable help on every route.
#
# Phase 21 — ``app/page.tsx`` was reduced to a server-side redirect
# (root → /characters) when the Dashboard tab was removed. It has no
# UI, so it's excluded from help/i18n assertions below.
REQUIRED_PAGES: tuple[Path, ...] = (
    FRONTEND / "app" / "jobs" / "page.tsx",                   # /jobs
    FRONTEND / "app" / "jobs" / "new" / "page.tsx",           # /jobs/new
    FRONTEND / "app" / "jobs" / "[jobId]" / "page.tsx",       # /jobs/[id]
    FRONTEND / "app" / "jobs" / "[jobId]" / "edit" / "page.tsx",
    FRONTEND / "app" / "uploads" / "page.tsx",                # /uploads
    FRONTEND / "app" / "settings" / "page.tsx",               # /settings
)

# Every typed API client function the dashboard uses (or that Phase 10C
# added so future pages don't reinvent the wrapper). Adding a row here
# without an export is a test failure on purpose — the parity doc is
# the source of truth.
REQUIRED_API_CLIENT_EXPORTS: tuple[str, ...] = (
    # System / config
    "getSystemStatus",
    "getUiOptions",
    "getStages",
    "getArtifactTypes",
    # Jobs
    "listJobs",
    "getJob",
    "getJobSummary",
    "getJobProgress",
    "getJobTimeline",
    "getJobArtifacts",
    "getJobComplianceEvents",
    "getJobQcReportOptional",
    "getJobFinalExportOptional",
    "createJob",
    "createJobFromInputs",
    "updateJob",
    "deleteJob",
    "cancelJob",
    "retryJob",
    # Uploads
    "uploadText",
    "uploadAudio",
    "uploadImage",
    # Providers
    "getProviders",
    "getProvidersForCategory",
    "getProviderDetail",
    # Generation
    "generateScript",
    "generateTts",
    "generateVideo",
    # Media tools
    "audioFitCheck",
    "inspectQc",
    "finalizeExport",
    # Helpers
    "artifactContentUrl",
    "humanizeApiDetail",
)

# Required components — surfaces that exist in the parity matrix.
REQUIRED_COMPONENTS: tuple[str, ...] = (
    "ArtifactTable.tsx",
    "AudioPreview.tsx",
    "BackendStatusBadge.tsx",
    "ComplianceEvents.tsx",
    "CreateJobForm.tsx",
    "CustomProvidersSection.tsx",
    "FinalExportCard.tsx",
    "HelpButton.tsx",
    "HelpHint.tsx",
    "HelpOverlay.tsx",
    "HelpContext.tsx",
    "JobRecoveryControls.tsx",
    "LogsPanel.tsx",
    "ProviderTestPanel.tsx",
    "ProvidersSection.tsx",
    "QcReportCard.tsx",
    "RightSidebar.tsx",
    "SettingsPanel.tsx",
    "SidebarTabs.tsx",
    "StageTimeline.tsx",
    "StatusBadge.tsx",
    "UploadCard.tsx",
    "VideoArtifactPreview.tsx",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_required_pages_exist():
    missing = [str(p.relative_to(REPO_ROOT)) for p in REQUIRED_PAGES if not p.is_file()]
    assert not missing, f"Missing pages in app/: {missing}"


def test_required_components_exist():
    cdir = FRONTEND / "components"
    missing = [c for c in REQUIRED_COMPONENTS if not (cdir / c).is_file()]
    assert not missing, f"Missing components: {missing}"


def test_pages_anchor_help():
    """Every required page must (a) be wrapped by the layout that mounts
    the global HelpButton, OR (b) embed a HelpHint of its own next to
    the h1. The layout-mounted FAB is sufficient — we check the layout
    once.
    """
    # Security remediation: the global help FAB moved into AppFrame.tsx
    # (the authenticated shell that layout.tsx delegates to). Every
    # authenticated page still inherits it.
    shell = _read(FRONTEND / "app" / "layout.tsx") + _read(
        FRONTEND / "components" / "AppFrame.tsx"
    )
    assert "<HelpButton" in shell, (
        "Global HelpButton must be rendered in the app shell "
        "(layout.tsx → AppFrame.tsx) so every page inherits the help FAB."
    )
    assert "HelpOverlay" in shell, (
        "HelpOverlay must be mounted at the shell level (AppFrame.tsx)."
    )

    # Page-level hints next to h1 — checked individually to make
    # regressions obvious in the failure message.
    for page in REQUIRED_PAGES:
        body = _read(page)
        # job/[id] + edit pages render the hint via cards, so allow either form.
        anchors = ("HelpHint", "HelpButton", "HelpLink")
        assert any(a in body for a in anchors), (
            f"{page.relative_to(REPO_ROOT)} does not import / render any help "
            f"anchor. Add a <HelpHint slug='...'/> next to its h1."
        )


def test_api_client_exports():
    """Static check that every required typed client function is
    declared in frontend/lib/api.ts. Catches accidental deletions and
    keeps the parity matrix honest.
    """
    src = _read(FRONTEND / "lib" / "api.ts")
    missing: list[str] = []
    for fn in REQUIRED_API_CLIENT_EXPORTS:
        # Recognise either "export function NAME" or "export async function NAME"
        # or "export const NAME = ...".
        signatures = (
            f"export function {fn}",
            f"export async function {fn}",
            f"export const {fn}",
        )
        if not any(sig in src for sig in signatures):
            missing.append(fn)
    assert not missing, (
        f"frontend/lib/api.ts is missing typed wrappers for: {missing}. "
        "Phase 10C requires every parity-matrix API to have a client function."
    )


def test_no_raw_fetch_in_pages_or_components():
    """The dashboard uses lib/api.ts. Raw window.fetch() in pages /
    components bypasses the structured-error humaniser and the log bus.
    Allow ``settings.ts`` (Test backend connection) which legitimately
    hits an arbitrary URL.
    """
    offenders: list[str] = []
    for root in (FRONTEND / "app", FRONTEND / "components"):
        for path in root.rglob("*.tsx"):
            text = _read(path)
            if "fetch(" in text and "// allow-raw-fetch" not in text:
                # SettingsPanel uses fetch to test arbitrary backend URLs —
                # that's intentional. Mark by allow-list.
                if path.name == "SettingsPanel.tsx":
                    continue
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"Raw fetch() in: {offenders}. Use frontend/lib/api.ts wrappers, "
        "or add `// allow-raw-fetch` if truly intentional (rare)."
    )


def test_help_link_in_nav():
    """The header nav must include a Help link, and the footer must too,
    so help is discoverable beyond the keyboard shortcut + FAB.

    Phase 11A: the layout delegates the nav to ``LocalizedNav`` which
    embeds ``HelpLink``; allow either spelling for the assertion so a
    future translation refactor doesn't break this guard.
    """
    layout = _read(FRONTEND / "app" / "layout.tsx")
    nav = _read(FRONTEND / "components" / "LocalizedNav.tsx") if (
        FRONTEND / "components" / "LocalizedNav.tsx"
    ).is_file() else ""
    assert "HelpLink" in layout or "HelpLink" in nav, (
        "The header nav must include a <HelpLink>. Add it to "
        "app/layout.tsx or to the LocalizedNav component the layout mounts."
    )


@pytest.mark.parametrize(
    "page_path,expected_slug",
    [
        # Phase 11A re-do: slugs renamed to match the brief vocabulary
        # in the new bilingual help corpora.
        # Phase 21 — app/page.tsx is now a server-side redirect, no
        # HelpHint to anchor; the dashboard help topic still exists
        # but documents its own removal.
        ("app/jobs/page.tsx", "jobs-list"),
        ("app/jobs/new/page.tsx", "create-job"),
        ("app/uploads/page.tsx", "uploads"),
        ("app/settings/page.tsx", "settings"),
    ],
)
def test_each_page_anchored_to_correct_help_slug(page_path: str, expected_slug: str):
    """The HelpHint slug on a page must point at the article that
    actually documents that page. This catches the common drift where
    someone copies a page and forgets to update the slug.
    """
    body = _read(FRONTEND / page_path)
    assert f'slug="{expected_slug}"' in body, (
        f"{page_path} should embed <HelpHint slug=\"{expected_slug}\" /> "
        "next to its <h1>. Update the page OR the parity matrix."
    )

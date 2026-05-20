"""Phase 11A (re-do) — static UI-uses-translation guard.

Verifies that the bilingual UI isn't just a switcher: every required
page and every required component actually imports ``useT`` and calls
``t(`` at least once. A button that doesn't change text when the
language changes can no longer ship.
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"


REQUIRED_PAGES = (
    # Phase 21 — app/page.tsx is now a server-side redirect with no
    # UI; excluded from the useT() requirement.
    FRONTEND / "app" / "jobs" / "page.tsx",
    FRONTEND / "app" / "jobs" / "new" / "page.tsx",
    FRONTEND / "app" / "jobs" / "[jobId]" / "page.tsx",
    FRONTEND / "app" / "jobs" / "[jobId]" / "edit" / "page.tsx",
    FRONTEND / "app" / "uploads" / "page.tsx",
    FRONTEND / "app" / "settings" / "page.tsx",
)

REQUIRED_COMPONENTS = (
    "CreateJobForm.tsx",
    "ArtifactTable.tsx",
    "AudioPreview.tsx",
    "VideoArtifactPreview.tsx",
    "QcReportCard.tsx",
    "FinalExportCard.tsx",
    "JobRecoveryControls.tsx",
    "UploadCard.tsx",
    "SettingsPanel.tsx",
    "ProvidersSection.tsx",
    "CustomProvidersSection.tsx",
    "ProviderTestPanel.tsx",
    "LogsPanel.tsx",
    "RightSidebar.tsx",
    "SidebarTabs.tsx",
    "HelpHint.tsx",
    "HelpButton.tsx",
    "HelpOverlay.tsx",
    "LocalizedNav.tsx",
    "LanguageSwitcher.tsx",
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_required_pages_exist():
    missing = [p for p in REQUIRED_PAGES if not p.is_file()]
    assert not missing, f"Missing pages: {[str(m.relative_to(REPO_ROOT)) for m in missing]}"


def test_required_components_exist():
    cdir = FRONTEND / "components"
    missing = [c for c in REQUIRED_COMPONENTS if not (cdir / c).is_file()]
    assert not missing, f"Missing components: {missing}"


@pytest.mark.parametrize("page", REQUIRED_PAGES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_pages_use_translation_hook(page: Path):
    body = _read(page)
    assert "useT" in body, (
        f"{page.relative_to(REPO_ROOT)} must import useT and call t() — "
        "otherwise the page text won't switch languages."
    )
    assert "t(" in body, f"{page.relative_to(REPO_ROOT)} imports useT but never calls t()."


@pytest.mark.parametrize("component", REQUIRED_COMPONENTS)
def test_components_use_translation_hook_or_switcher(component: str):
    """Every operator-facing component must either:
    - import useT and call t() at least once, OR
    - be a translation primitive itself (LanguageSwitcher).
    """
    body = _read(FRONTEND / "components" / component)
    is_primitive = component in (
        "LanguageSwitcher.tsx",  # the switcher itself
    )
    if is_primitive:
        return
    has_useT = "useT" in body
    has_t_call = "t(" in body
    assert has_useT, (
        f"{component} does not import useT — it cannot be bilingual. "
        f"Add `import {{ useT }} from \"@/lib/i18n/LanguageContext\";` "
        "and call t() on at least one visible string."
    )
    assert has_t_call, (
        f"{component} imports useT but never calls t() — every required "
        "component must translate at least one user-visible string."
    )


def test_language_provider_in_app():
    """The layout must render LanguageProvider somewhere in the tree."""
    providers = _read(FRONTEND / "components" / "Providers.tsx")
    assert "LanguageProvider" in providers, (
        "Providers.tsx must mount LanguageProvider so the whole tree can "
        "call useT()."
    )


def test_layout_renders_language_switcher():
    layout = _read(FRONTEND / "app" / "layout.tsx")
    # The switcher itself OR the localised nav wrapper that mounts it.
    has = "LanguageSwitcher" in layout or "HeaderRight" in layout
    assert has, (
        "app/layout.tsx must render the LanguageSwitcher (directly or via "
        "HeaderRight) so the operator can change languages."
    )


def test_i18n_index_exports_useT():
    src = _read(FRONTEND / "lib" / "i18n" / "index.ts")
    assert "useT" in src
    assert "useLanguage" in src
    assert "LanguageProvider" in src


def test_dictionaries_subfolder_path():
    """``dictionaries/`` must be the home of both UI and Help corpora —
    that's what the brief requires."""
    assert (FRONTEND / "lib" / "i18n" / "dictionaries" / "en.ts").is_file()
    assert (FRONTEND / "lib" / "i18n" / "dictionaries" / "ro.ts").is_file()
    assert (FRONTEND / "lib" / "help" / "dictionaries" / "en.ts").is_file()
    assert (FRONTEND / "lib" / "help" / "dictionaries" / "ro.ts").is_file()

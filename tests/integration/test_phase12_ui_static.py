"""Phase 12 — Static UI invariants for the Characters tab.

- Characters page exists.
- Characters tab is linked from the navigation.
- Character dropdown is present in CreateJobForm.
- /api/v1/providers is invoked for image_generator from the character
  image library (no hardcoded provider arrays in the frontend).
- Every visible string in the new components goes through ``useT()``.
- ``HelpHint`` reads from the localized corpus directly (Phase 12 fix
  for the EN-fallback bug).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"


def _read(path: str) -> str:
    return (FRONTEND / path).read_text(encoding="utf-8")


def test_characters_pages_exist():
    assert (FRONTEND / "app" / "characters" / "page.tsx").is_file()
    assert (FRONTEND / "app" / "characters" / "new" / "page.tsx").is_file()
    assert (FRONTEND / "app" / "characters" / "[id]" / "page.tsx").is_file()


def test_localized_nav_links_to_characters():
    src = _read("components/LocalizedNav.tsx")
    assert '/characters' in src
    assert 't("nav.characters")' in src


def test_create_job_form_has_character_dropdown():
    src = _read("components/CreateJobForm.tsx")
    # Look for the data-testid we added on the dropdown.
    assert 'data-testid="character-dropdown"' in src
    # And the body must carry character_id through to the request.
    assert 'character_id: characterId' in src or 'character_id: characterId || null' in src


def test_image_library_pulls_providers_from_api_not_hardcoded():
    src = _read("components/CharacterImageLibrary.tsx")
    # Must call api.getProviders() (dynamic registry), not hardcode FLUX/SD3.5.
    assert "api.getProviders" in src
    # No literal provider lists baked in the JSX (no spec-banned hardcoded arrays).
    forbidden = re.findall(r'\[\s*"flux_local"\s*,\s*"flux_bfl_api"', src)
    assert not forbidden, "providers must come from /api/v1/providers, not a hardcoded array"


def test_character_form_uses_useT_for_every_visible_label():
    src = _read("components/CharacterForm.tsx")
    # Spot-check a few key labels — every one must come from i18n.
    for needle in (
        't("characters.sections.identity")',
        't("characters.sections.appearance")',
        't("characters.sections.personality")',
        't("characters.fields.gender")',
        't("characters.fields.archetype")',
        't("providerStatus.selectProvider")',
    ):
        assert needle in src, f"missing i18n call: {needle}"


def test_help_hint_reads_localized_corpus_not_getHelpTopic_fallback():
    # The Phase 12 fix: HelpHint must NOT call getHelpTopic() (which
    # falls back to EN), it must read the current-language corpus
    # directly. Otherwise tooltip titles leak English when a topic is
    # missing from the RO corpus.
    src = _read("components/HelpHint.tsx")
    assert "getLocalizedHelpCorpus" in src
    # Strip JS line comments before scanning so the rationale comment
    # that explains the bug (and necessarily mentions the function
    # name) doesn't trip the regex.
    no_comments = re.sub(r"//.*", "", src)
    assert "getHelpTopic(" not in no_comments
    assert "from \"@/lib/help/dictionaries\"" in src
    # Import line must not re-import getHelpTopic.
    import_line = next((l for l in src.splitlines() if "from \"@/lib/help/dictionaries\"" in l), "")
    assert "getHelpTopic" not in import_line


def test_provider_status_badge_exists_and_uses_i18n():
    src = _read("components/ProviderStatusBadge.tsx")
    assert 't(`providerStatus.${status}`)' in src
    assert 'role="status"' in src


def test_new_help_topics_exist_in_both_languages():
    en = _read("lib/help/dictionaries/en.ts")
    ro = _read("lib/help/dictionaries/ro.ts")
    for slug in (
        "characters",
        "character-image-library",
        "character-image-provider",
        "character-main-reference",
        "video-character",
        "providers-overview",
    ):
        assert f'id: "{slug}"' in en, f"missing help slug {slug} in en.ts"
        assert f'id: "{slug}"' in ro, f"missing help slug {slug} in ro.ts"


def test_i18n_dictionary_parity_for_characters_blocks():
    en = _read("lib/i18n/dictionaries/en.ts")
    ro = _read("lib/i18n/dictionaries/ro.ts")
    # Top-level blocks present in both.
    for top in ("characters:", "characterLookups:", "providerStatus:", "videoCharacter:"):
        assert top in en, f"{top} missing from en.ts"
        assert top in ro, f"{top} missing from ro.ts"


def test_image_generator_in_frontend_types():
    src = _read("lib/types.ts")
    assert '"image_generator"' in src
    assert "image_generator_id" in src


def test_characters_api_client_exists():
    src = _read("lib/characters.ts")
    for needle in (
        "listCharacters",
        "createCharacter",
        "updateCharacter",
        "deleteCharacter",
        "generateCharacterImage",
        "setCharacterImageStatus",
        "getCharacterLookups",
        "getCharacterScriptContext",
    ):
        assert f"export function {needle}" in src or f"export async function {needle}" in src

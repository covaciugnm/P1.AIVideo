"""Phase 16 — build English appearance prompt from CharacterProfile.

When a character has a locked sample face (main_reference_image_id set),
every subsequent image generation must produce the same face. We help
the diffusion model along by **prepending** an English description of
the person's appearance (built from the character's profile fields)
to the operator-supplied scene prompt.

The operator's prompt then only needs to describe the SCENE / context
(e.g. ``walking in heavy rain on a city street, dramatic lighting``),
not the person.

Output is plain English, comma-separated phrases — the format diffusion
models digest best.
"""
from __future__ import annotations

from typing import Any


def _val(profile: dict[str, Any], section: str, key: str) -> str | None:
    """Safe nested getter — returns trimmed string or None."""
    sec = profile.get(section) if isinstance(profile, dict) else None
    if not isinstance(sec, dict):
        return None
    v = sec.get(key)
    if not isinstance(v, str):
        return None
    v = v.strip()
    return v or None


def build_person_description_en(profile_json: dict[str, Any] | None) -> str:
    """Compose an English appearance prompt from the character profile.

    Returns an empty string when the profile is empty / missing.
    """
    if not profile_json:
        return ""

    bits: list[str] = []

    # Identity → gender + age range
    gender = _val(profile_json, "identity", "gender")
    age_val = profile_json.get("identity", {}).get("age") if isinstance(profile_json.get("identity"), dict) else None
    if isinstance(age_val, int) and age_val > 0:
        if age_val < 18:
            age_desc = "teenager"
        elif age_val < 30:
            age_desc = "young adult"
        elif age_val < 45:
            age_desc = "adult in their 30s-40s"
        elif age_val < 60:
            age_desc = "middle-aged"
        else:
            age_desc = "older adult"
    else:
        age_desc = None

    person_noun = "person"
    g = (gender or "").lower()
    if g in ("female", "femeie", "f", "woman"):
        person_noun = "woman"
    elif g in ("male", "barbat", "bărbat", "m", "man"):
        person_noun = "man"
    elif g in ("non-binary", "nonbinary"):
        person_noun = "non-binary person"
    if age_desc:
        bits.append(f"the same {age_desc} {person_noun}")
    else:
        bits.append(f"the same {person_noun}")

    # Appearance
    for sec, key, prefix in [
        ("appearance", "skin_tone", ""),
        ("appearance", "hair_color", ""),
        ("appearance", "hair_style", ""),
        ("appearance", "eye_color", "with"),
        ("appearance", "face_shape", "with a"),
        ("appearance", "height", ""),
        ("appearance", "weight_or_build", ""),
        ("appearance", "distinctive_features", ""),
        ("appearance", "clothing_style", "wearing"),
    ]:
        v = _val(profile_json, sec, key)
        if v:
            phrase = (prefix + " " + v).strip() if prefix else v
            if key == "hair_color":
                phrase = f"{v} hair"
            if key == "eye_color":
                phrase = f"with {v} eyes"
            if key == "face_shape":
                phrase = f"with a {v} face"
            bits.append(phrase)

    consistency = _val(profile_json, "appearance", "visual_consistency_notes")
    if consistency:
        bits.append(consistency)

    return ", ".join(bits)


def merge_scene_with_person(person_desc: str, scene_prompt: str | None) -> str:
    """Combine the auto-built person description with the operator's scene
    prompt into a single comma-separated prompt the model can ingest."""
    parts: list[str] = []
    if person_desc:
        parts.append(person_desc)
    if scene_prompt and scene_prompt.strip():
        parts.append(scene_prompt.strip())
    return ", ".join(parts)


def build_negative_constraints_en(profile_json: dict[str, Any] | None) -> str:
    """Pull the character's ``negative_visual_constraints`` field if present.

    Returned text is appended after the operator's own negative_prompt.
    """
    if not profile_json:
        return ""
    return _val(profile_json, "appearance", "negative_visual_constraints") or ""

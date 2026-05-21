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


# ---------------------------------------------------------------------------
# Phase IG-2 — identity-locked builder for the ComfyUI consistent pipeline.
#
# Splits IMMUTABLE identity (from the profile) from MUTABLE scene params
# (per request). Reuses ``build_person_description_en`` for the identity
# descriptors so the two code paths stay consistent.
# ---------------------------------------------------------------------------

from dataclasses import dataclass  # noqa: E402

_IDENTITY_NEGATIVES = (
    "different person, face swap, identity change, age change, younger, older, "
    "distorted face, deformed face, asymmetric eyes, extra face, duplicate face, "
    "plastic skin, waxy skin, distorted hands, extra fingers, extra limbs, "
    "missing limbs, mutated, lowres, blurry, watermark, text"
)
_COMPLIANCE_NEGATIVE = "real person, celebrity, public figure, real-person likeness"


@dataclass(frozen=True)
class SceneParams:
    """Mutable, per-request scene description."""

    scene_prompt: str = ""
    outfit_prompt: str = ""
    location_prompt: str = ""
    season: str = ""
    time_of_day: str = ""
    weather: str = ""
    head_wear: str = ""
    mood: str = ""
    pose: str = ""
    framing: str = ""
    negative_prompt_extra: str = ""


def _join(parts: list[str | None]) -> str:
    return ", ".join(p.strip() for p in parts if p and str(p).strip())


def build_identity_block(profile_json: dict[str, Any] | None) -> str:
    desc = build_person_description_en(profile_json)
    lock = (
        "IDENTITY LOCK: the same synthetic character; preserve facial identity, "
        "apparent age range, face shape, eye shape, nose, mouth, jawline, skin "
        "tone, hairstyle identity and natural body proportions; do not turn this "
        "into a different person."
    )
    return f"{lock} CHARACTER: {desc}." if desc else lock


def build_scene_block(profile_json: dict[str, Any] | None, scene: SceneParams) -> str:
    p = profile_json or {}
    sb = p.get("script_behaviour") if isinstance(p.get("script_behaviour"), dict) else {}
    appe = p.get("appearance") if isinstance(p.get("appearance"), dict) else {}
    outfit = scene.outfit_prompt or appe.get("clothing_style") or ""
    location = scene.location_prompt or sb.get("default_background") or ""
    return _join(
        [
            scene.scene_prompt,
            f"wearing {outfit}" if outfit else None,
            f"with {scene.head_wear}" if scene.head_wear else None,
            f"in {location}" if location else None,
            scene.season,
            scene.time_of_day,
            f"{scene.weather} weather" if scene.weather else None,
            scene.pose,
            f"{scene.mood} expression" if scene.mood else None,
        ]
    )


def build_style_block(profile_json: dict[str, Any] | None, scene: SceneParams) -> str:
    p = profile_json or {}
    sb = p.get("script_behaviour") if isinstance(p.get("script_behaviour"), dict) else {}
    framing = scene.framing or sb.get("default_camera_framing") or "natural framing"
    return _join(
        [
            "photorealistic, high detail, natural lighting, professional photography",
            framing,
            sb.get("default_mood"),
        ]
    )


def build_negative_block(profile_json: dict[str, Any] | None, scene: SceneParams) -> str:
    return _join(
        [
            _IDENTITY_NEGATIVES,
            _COMPLIANCE_NEGATIVE,
            build_negative_constraints_en(profile_json),
            scene.negative_prompt_extra,
        ]
    )


def build_consistent_prompt(
    profile_json: dict[str, Any] | None, scene: SceneParams
) -> tuple[str, str]:
    """Return ``(positive, negative)`` for identity-consistent generation."""
    positive = " ".join(
        [
            build_identity_block(profile_json),
            f"SCENE: {build_scene_block(profile_json, scene)}.",
            f"STYLE: {build_style_block(profile_json, scene)}.",
            "REFERENCE USAGE: use the face reference for facial identity and the "
            "full-body reference for body proportions and silhouette.",
        ]
    )
    return positive.strip(), build_negative_block(profile_json, scene)


def build_initial_prompt(
    profile_json: dict[str, Any] | None,
) -> tuple[str, str]:
    """First-image prompt: identity descriptors only (no reference yet)."""
    positive = (
        f"{build_identity_block(profile_json)} "
        "SCENE: neutral studio portrait, plain background. "
        f"STYLE: {build_style_block(profile_json, SceneParams())}."
    )
    return positive.strip(), build_negative_block(profile_json, SceneParams())

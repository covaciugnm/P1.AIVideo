"""Character → LLM script context — Phase 12 (Phase D).

Turns a :class:`CharacterProfile` (or the JSON snapshot stored on a
job) into a clean structured prompt fragment the scriptwriter can
inject when generating dialogue / narration.

Design rules:
- Plain prose, not raw JSON. The LLM gets a paragraph-shaped briefing.
- Empty / N/A fields are omitted (the LLM doesn't see ``"hair_color: None"``).
- ``allowed_topics`` / ``blocked_topics`` are surfaced as explicit guard rails.
- The output is deterministic given the same profile.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.schemas.character import (
    CharacterProfile,
    CharacterScriptContextResponse,
)


def _bullet(label: str, value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, (list, tuple)):
        cleaned = [str(x).strip() for x in value if str(x).strip()]
        if not cleaned:
            return None
        value = ", ".join(cleaned)
    return f"- {label}: {value}"


def build_character_script_context(
    profile: CharacterProfile,
    *,
    character_id: uuid.UUID | None = None,
) -> CharacterScriptContextResponse:
    identity = profile.identity
    appearance = profile.appearance
    education = profile.education
    personality = profile.personality
    voice = profile.voice
    behaviour = profile.script_behaviour

    sections: list[str] = []

    # --- Who they are ---
    who = [f"## Character briefing"]
    who.append(
        f"You are writing dialogue / narration for **{identity.display_name or identity.name}**."
    )
    age = profile.computed_age()
    if age is not None:
        who.append(
            f"They are roughly {age} years old."
        )
    if identity.gender:
        who.append(f"Gender: {identity.gender}.")
    if identity.nationality:
        who.append(f"Nationality: {identity.nationality}.")
    if identity.current_location:
        who.append(f"Currently based in: {identity.current_location}.")
    if identity.is_public_persona:
        who.append(
            "This is a public persona — keep statements consistent across videos."
        )
    sections.append("\n".join(who))

    # --- Language ---
    lang_lines: list[str] = ["## Language"]
    if identity.native_language:
        lang_lines.append(f"- Native language: {identity.native_language}")
    if identity.spoken_languages:
        lang_lines.append(
            f"- Spoken languages: {', '.join(identity.spoken_languages)}"
        )
    if voice.preferred_language:
        lang_lines.append(f"- Preferred for this video: {voice.preferred_language}")
    if voice.accent:
        lang_lines.append(f"- Accent: {voice.accent}")
    if len(lang_lines) > 1:
        sections.append("\n".join(lang_lines))

    # --- How they speak / personality ---
    voice_bits = [
        _bullet("Communication style", personality.communication_style),
        _bullet("Tone", personality.emotional_tone or voice.tone),
        _bullet("Temperament", personality.temperament),
        _bullet("Formality", personality.formality_level),
        _bullet("Humor", personality.humor_level),
        _bullet("Confidence", personality.confidence_level),
        _bullet("Empathy", personality.empathy_level),
        _bullet("Assertiveness", personality.assertiveness_level),
        _bullet("Patience", personality.patience_level),
        _bullet("Pitch", voice.pitch),
        _bullet("Speaking speed", voice.speaking_speed),
    ]
    voice_bits = [b for b in voice_bits if b]
    if voice_bits:
        sections.append("## How they speak\n" + "\n".join(voice_bits))

    # --- What they know ---
    know_bits = [
        _bullet("Education level", education.education_level),
        _bullet("Field of study", education.field_of_study),
        _bullet("Occupation", education.occupation),
        _bullet("Current role", education.current_role),
        _bullet("Industry / domain", education.industry_domain),
        _bullet("Expertise areas", education.expertise),
        _bullet("Seniority", education.professional_seniority),
        _bullet("Authority level", education.authority_level),
    ]
    know_bits = [b for b in know_bits if b]
    if know_bits:
        sections.append("## What they know\n" + "\n".join(know_bits))
    if education.cv_summary and education.cv_summary.strip():
        sections.append(f"## CV summary\n{education.cv_summary.strip()}")

    # --- Social / role context ---
    role_bits = [
        _bullet("Social status", identity.social_status),
        _bullet("Marital status", identity.marital_status),
        _bullet("Narrative role", personality.narrative_role or behaviour.default_role_in_videos),
        _bullet("Default mood", behaviour.default_mood),
        _bullet("Default camera framing", behaviour.default_camera_framing),
        _bullet("Default background / environment", behaviour.default_background),
        _bullet("Default topic expertise", behaviour.default_topic_expertise),
    ]
    role_bits = [b for b in role_bits if b]
    if role_bits:
        sections.append("## Role & framing\n" + "\n".join(role_bits))

    # --- Personality narrative ---
    personality_lines: list[str] = []
    if personality.archetype:
        personality_lines.append(f"Archetype: {personality.archetype}.")
    if personality.moral_values and personality.moral_values.strip():
        personality_lines.append(f"Values: {personality.moral_values.strip()}")
    if personality.motivations and personality.motivations.strip():
        personality_lines.append(f"Motivations: {personality.motivations.strip()}")
    if personality.goals and personality.goals.strip():
        personality_lines.append(f"Goals: {personality.goals.strip()}")
    if personality.fears and personality.fears.strip():
        personality_lines.append(f"Fears / weaknesses: {personality.fears.strip()}")
    if personality.conflict_style:
        personality_lines.append(f"Conflict style: {personality.conflict_style}.")
    if personality.decision_style:
        personality_lines.append(f"Decision style: {personality.decision_style}.")
    if personality_lines:
        sections.append("## Personality\n" + "\n".join(f"- {line}" for line in personality_lines))

    # --- Appearance continuity ---
    appearance_bits = [
        _bullet("Hair colour", appearance.hair_color),
        _bullet("Hair style", appearance.hair_style),
        _bullet("Eye colour", appearance.eye_color),
        _bullet("Skin tone", appearance.skin_tone),
        _bullet("Face shape", appearance.face_shape),
        _bullet("Build / height", appearance.height or appearance.weight_or_build),
        _bullet("Clothing style", appearance.clothing_style),
        _bullet("Distinctive features", appearance.distinctive_features),
    ]
    appearance_bits = [b for b in appearance_bits if b]
    if appearance_bits:
        sections.append(
            "## Visual continuity (do not contradict)\n"
            + "\n".join(appearance_bits)
        )
    if appearance.visual_consistency_notes and appearance.visual_consistency_notes.strip():
        sections.append(
            "## Visual consistency notes\n"
            + appearance.visual_consistency_notes.strip()
        )
    if appearance.negative_visual_constraints and appearance.negative_visual_constraints.strip():
        sections.append(
            "## Negative visual constraints (must not change)\n"
            + appearance.negative_visual_constraints.strip()
        )

    # --- Safety / topic guard rails ---
    guard: list[str] = []
    if behaviour.allowed_topics:
        guard.append(
            "Allowed topics: " + ", ".join(behaviour.allowed_topics) + "."
        )
    if behaviour.blocked_topics:
        guard.append(
            "Blocked topics (NEVER discuss): "
            + ", ".join(behaviour.blocked_topics)
            + "."
        )
    if behaviour.safety_notes and behaviour.safety_notes.strip():
        guard.append(behaviour.safety_notes.strip())
    if guard:
        sections.append("## Safety & topic guard rails\n" + "\n".join(f"- {g}" for g in guard))

    # --- Script style notes ---
    if behaviour.prompt_style_notes and behaviour.prompt_style_notes.strip():
        sections.append("## Prompt style notes\n" + behaviour.prompt_style_notes.strip())
    if behaviour.script_generation_notes and behaviour.script_generation_notes.strip():
        sections.append(
            "## Script generation notes\n" + behaviour.script_generation_notes.strip()
        )

    text = "\n\n".join(sections).strip()
    fields = profile.model_dump(mode="json")
    return CharacterScriptContextResponse(
        character_id=character_id or uuid.UUID(int=0),
        text=text,
        fields=fields,
    )

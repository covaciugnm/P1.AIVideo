"""Translatable dropdown options for the character profile form — Phase 12.

These are the canonical option lists exposed via
``GET /api/v1/characters/lookups``. The frontend resolves
``label_key`` through ``useT()`` so the dropdown text follows the
operator UI language (RO/EN). ``label_en`` / ``label_ro`` are also
served so external integrations can read a bilingual label without
the UI round-trip.
"""
from __future__ import annotations

from app.schemas.character import CharacterLookupsResponse, LookupOption


def _opt(value: str, key: str, en: str, ro: str) -> LookupOption:
    return LookupOption(value=value, label_key=key, label_en=en, label_ro=ro)


# Each list is intentionally short + canonical. Operators who need a
# rarer option can type the free-text alternative directly in the
# profile form — schemas accept open strings.
_GENDER = [
    _opt("female", "characterLookups.gender.female", "Female", "Feminin"),
    _opt("male", "characterLookups.gender.male", "Male", "Masculin"),
    _opt("non_binary", "characterLookups.gender.non_binary", "Non-binary", "Non-binar"),
    _opt(
        "prefer_not_to_say",
        "characterLookups.gender.prefer_not_to_say",
        "Prefer not to say",
        "Prefer să nu spun",
    ),
    _opt("other", "characterLookups.gender.other", "Other", "Altul"),
]

_MARITAL = [
    _opt("single", "characterLookups.marital.single", "Single", "Necăsătorit"),
    _opt("married", "characterLookups.marital.married", "Married", "Căsătorit"),
    _opt("partnered", "characterLookups.marital.partnered", "In a relationship", "Într-o relație"),
    _opt("divorced", "characterLookups.marital.divorced", "Divorced", "Divorțat"),
    _opt("widowed", "characterLookups.marital.widowed", "Widowed", "Văduv"),
    _opt(
        "prefer_not_to_say",
        "characterLookups.marital.prefer_not_to_say",
        "Prefer not to say",
        "Prefer să nu spun",
    ),
]

_EDUCATION = [
    _opt("none", "characterLookups.education.none", "None", "Niciuna"),
    _opt("primary", "characterLookups.education.primary", "Primary", "Primară"),
    _opt("secondary", "characterLookups.education.secondary", "Secondary", "Liceu"),
    _opt(
        "vocational",
        "characterLookups.education.vocational",
        "Vocational",
        "Învățământ profesional",
    ),
    _opt("bachelors", "characterLookups.education.bachelors", "Bachelor's", "Licență"),
    _opt("masters", "characterLookups.education.masters", "Master's", "Master"),
    _opt("phd", "characterLookups.education.phd", "PhD / Doctorate", "Doctorat"),
    _opt(
        "post_doc",
        "characterLookups.education.post_doc",
        "Post-doctoral",
        "Post-doctorat",
    ),
    _opt("self_taught", "characterLookups.education.self_taught", "Self-taught", "Autodidact"),
]

_SOCIAL_STATUS = [
    _opt("working_class", "characterLookups.social.working_class", "Working class", "Clasă muncitoare"),
    _opt("middle_class", "characterLookups.social.middle_class", "Middle class", "Clasă mijlocie"),
    _opt(
        "upper_middle_class",
        "characterLookups.social.upper_middle_class",
        "Upper-middle class",
        "Clasă mijlocie-superioară",
    ),
    _opt("upper_class", "characterLookups.social.upper_class", "Upper class", "Clasă superioară"),
    _opt("public_figure", "characterLookups.social.public_figure", "Public figure", "Figură publică"),
    _opt("entrepreneur", "characterLookups.social.entrepreneur", "Entrepreneur", "Antreprenor"),
    _opt("student", "characterLookups.social.student", "Student", "Student"),
    _opt("retired", "characterLookups.social.retired", "Retired", "Pensionar"),
]

_SENIORITY = [
    _opt("junior", "characterLookups.seniority.junior", "Junior", "Junior"),
    _opt("mid", "characterLookups.seniority.mid", "Mid-level", "Intermediar"),
    _opt("senior", "characterLookups.seniority.senior", "Senior", "Senior"),
    _opt("lead", "characterLookups.seniority.lead", "Lead", "Lead"),
    _opt("principal", "characterLookups.seniority.principal", "Principal", "Principal"),
    _opt("director", "characterLookups.seniority.director", "Director", "Director"),
    _opt("vp", "characterLookups.seniority.vp", "VP", "VP"),
    _opt("c_level", "characterLookups.seniority.c_level", "C-level", "C-level"),
    _opt("founder", "characterLookups.seniority.founder", "Founder", "Fondator"),
]

_AUTHORITY = [
    _opt("low", "characterLookups.authority.low", "Low", "Scăzut"),
    _opt("medium", "characterLookups.authority.medium", "Medium", "Mediu"),
    _opt("high", "characterLookups.authority.high", "High", "Ridicat"),
    _opt("recognised_expert", "characterLookups.authority.expert", "Recognised expert", "Expert recunoscut"),
]

_ARCHETYPE = [
    _opt("teacher", "characterLookups.archetype.teacher", "Teacher / Mentor", "Profesor / Mentor"),
    _opt("expert", "characterLookups.archetype.expert", "Expert / Specialist", "Expert / Specialist"),
    _opt("storyteller", "characterLookups.archetype.storyteller", "Storyteller", "Povestitor"),
    _opt("entertainer", "characterLookups.archetype.entertainer", "Entertainer", "Entertainer"),
    _opt("analyst", "characterLookups.archetype.analyst", "Analyst", "Analist"),
    _opt("activist", "characterLookups.archetype.activist", "Activist / Advocate", "Activist"),
    _opt("explorer", "characterLookups.archetype.explorer", "Explorer", "Explorator"),
    _opt("caregiver", "characterLookups.archetype.caregiver", "Caregiver", "Îngrijitor"),
    _opt("rebel", "characterLookups.archetype.rebel", "Rebel", "Rebel"),
    _opt("ruler", "characterLookups.archetype.ruler", "Ruler / Leader", "Conducător"),
]

_COMM_STYLE = [
    _opt("formal", "characterLookups.commStyle.formal", "Formal", "Formal"),
    _opt("informal", "characterLookups.commStyle.informal", "Informal", "Informal"),
    _opt("conversational", "characterLookups.commStyle.conversational", "Conversational", "Conversațional"),
    _opt("authoritative", "characterLookups.commStyle.authoritative", "Authoritative", "Autoritar"),
    _opt("persuasive", "characterLookups.commStyle.persuasive", "Persuasive", "Persuasiv"),
    _opt("playful", "characterLookups.commStyle.playful", "Playful", "Jucăuș"),
    _opt("technical", "characterLookups.commStyle.technical", "Technical", "Tehnic"),
    _opt("educational", "characterLookups.commStyle.educational", "Educational", "Educativ"),
]

_TEMPERAMENT = [
    _opt("sanguine", "characterLookups.temperament.sanguine", "Sanguine", "Sangvinic"),
    _opt("choleric", "characterLookups.temperament.choleric", "Choleric", "Coleric"),
    _opt("melancholic", "characterLookups.temperament.melancholic", "Melancholic", "Melancolic"),
    _opt("phlegmatic", "characterLookups.temperament.phlegmatic", "Phlegmatic", "Flegmatic"),
    _opt("balanced", "characterLookups.temperament.balanced", "Balanced", "Echilibrat"),
]

_TONE = [
    _opt("neutral", "characterLookups.tone.neutral", "Neutral", "Neutru"),
    _opt("warm", "characterLookups.tone.warm", "Warm", "Cald"),
    _opt("cold", "characterLookups.tone.cold", "Cold", "Rece"),
    _opt("serious", "characterLookups.tone.serious", "Serious", "Serios"),
    _opt("humorous", "characterLookups.tone.humorous", "Humorous", "Umoristic"),
    _opt("sarcastic", "characterLookups.tone.sarcastic", "Sarcastic", "Sarcastic"),
    _opt("inspirational", "characterLookups.tone.inspirational", "Inspirational", "Inspirațional"),
    _opt("urgent", "characterLookups.tone.urgent", "Urgent", "Urgent"),
]

_LEVEL_SCALE = [
    _opt("very_low", "characterLookups.level.very_low", "Very low", "Foarte scăzut"),
    _opt("low", "characterLookups.level.low", "Low", "Scăzut"),
    _opt("medium", "characterLookups.level.medium", "Medium", "Mediu"),
    _opt("high", "characterLookups.level.high", "High", "Ridicat"),
    _opt("very_high", "characterLookups.level.very_high", "Very high", "Foarte ridicat"),
]

_CONFLICT_STYLE = [
    _opt("avoidant", "characterLookups.conflict.avoidant", "Avoidant", "Evitant"),
    _opt("accommodating", "characterLookups.conflict.accommodating", "Accommodating", "Acomodant"),
    _opt("collaborative", "characterLookups.conflict.collaborative", "Collaborative", "Colaborativ"),
    _opt("competitive", "characterLookups.conflict.competitive", "Competitive", "Competitiv"),
    _opt("compromising", "characterLookups.conflict.compromising", "Compromising", "De compromis"),
]

_DECISION_STYLE = [
    _opt("analytical", "characterLookups.decision.analytical", "Analytical", "Analitic"),
    _opt("intuitive", "characterLookups.decision.intuitive", "Intuitive", "Intuitiv"),
    _opt("consultative", "characterLookups.decision.consultative", "Consultative", "Consultativ"),
    _opt("directive", "characterLookups.decision.directive", "Directive", "Directiv"),
    _opt("consensus", "characterLookups.decision.consensus", "Consensus-driven", "Bazat pe consens"),
]

_NARRATIVE_ROLE = [
    _opt("presenter", "characterLookups.role.presenter", "Presenter", "Prezentator"),
    _opt("expert", "characterLookups.role.expert", "Expert", "Expert"),
    _opt("narrator", "characterLookups.role.narrator", "Narrator", "Narator"),
    _opt("adversary", "characterLookups.role.adversary", "Adversary", "Adversar"),
    _opt("teacher", "characterLookups.role.teacher", "Teacher", "Profesor"),
    _opt("customer", "characterLookups.role.customer", "Customer", "Client"),
    _opt("founder", "characterLookups.role.founder", "Founder", "Fondator"),
    _opt("politician", "characterLookups.role.politician", "Politician", "Politician"),
    _opt("doctor", "characterLookups.role.doctor", "Doctor", "Medic"),
    _opt("engineer", "characterLookups.role.engineer", "Engineer", "Inginer"),
    _opt("journalist", "characterLookups.role.journalist", "Journalist", "Jurnalist"),
    _opt("interviewer", "characterLookups.role.interviewer", "Interviewer", "Intervievator"),
]

_VOICE_GENDER = [
    _opt("female", "characterLookups.voiceGender.female", "Female voice", "Voce feminină"),
    _opt("male", "characterLookups.voiceGender.male", "Male voice", "Voce masculină"),
    _opt("neutral", "characterLookups.voiceGender.neutral", "Neutral voice", "Voce neutră"),
]

_VOICE_AGE = [
    _opt("child", "characterLookups.voiceAge.child", "Child", "Copil"),
    _opt("teen", "characterLookups.voiceAge.teen", "Teen", "Adolescent"),
    _opt("young_adult", "characterLookups.voiceAge.young_adult", "Young adult", "Tânăr adult"),
    _opt("adult", "characterLookups.voiceAge.adult", "Adult", "Adult"),
    _opt("middle_aged", "characterLookups.voiceAge.middle_aged", "Middle-aged", "Vârstă mijlocie"),
    _opt("senior", "characterLookups.voiceAge.senior", "Senior", "Vârstnic"),
]

_SPEAKING_SPEED = [
    _opt("slow", "characterLookups.speed.slow", "Slow", "Lent"),
    _opt("medium", "characterLookups.speed.medium", "Medium", "Mediu"),
    _opt("fast", "characterLookups.speed.fast", "Fast", "Rapid"),
]

_PITCH = [
    _opt("low", "characterLookups.pitch.low", "Low pitch", "Voce joasă"),
    _opt("medium", "characterLookups.pitch.medium", "Medium pitch", "Voce medie"),
    _opt("high", "characterLookups.pitch.high", "High pitch", "Voce înaltă"),
]

_CAMERA_FRAMING = [
    _opt("close_up", "characterLookups.framing.close_up", "Close-up", "Prim-plan"),
    _opt("medium_shot", "characterLookups.framing.medium_shot", "Medium shot", "Plan mediu"),
    _opt("wide_shot", "characterLookups.framing.wide_shot", "Wide shot", "Plan larg"),
    _opt("over_shoulder", "characterLookups.framing.over_shoulder", "Over-the-shoulder", "Peste umăr"),
]

_MOOD = [
    _opt("neutral", "characterLookups.mood.neutral", "Neutral", "Neutru"),
    _opt("positive", "characterLookups.mood.positive", "Positive", "Pozitiv"),
    _opt("serious", "characterLookups.mood.serious", "Serious", "Serios"),
    _opt("urgent", "characterLookups.mood.urgent", "Urgent", "Urgent"),
    _opt("playful", "characterLookups.mood.playful", "Playful", "Jucăuș"),
    _opt("inspirational", "characterLookups.mood.inspirational", "Inspirational", "Inspirațional"),
]

_CHARACTER_STATUS = [
    # Phase 23 lifecycle order: editing → active → retired (legacy
    # inactive/draft kept so historical rows still resolve a label).
    _opt("editing", "characterLookups.status.editing", "Editing", "În editare"),
    _opt("active", "characterLookups.status.active", "Active", "Activ"),
    _opt("retired", "characterLookups.status.retired", "Retired", "Retras"),
    _opt("inactive", "characterLookups.status.inactive", "Inactive", "Inactiv"),
    _opt("draft", "characterLookups.status.draft", "Draft", "Schiță"),
]

_IMAGE_STATUS = [
    _opt("draft", "characterLookups.imageStatus.draft", "Draft", "Schiță"),
    _opt("accepted", "characterLookups.imageStatus.accepted", "Accepted", "Acceptată"),
    _opt("rejected", "characterLookups.imageStatus.rejected", "Rejected", "Respinsă"),
    _opt("reference", "characterLookups.imageStatus.reference", "Reference", "Referință"),
    _opt("archived", "characterLookups.imageStatus.archived", "Archived", "Arhivată"),
]

# Mirror the languages already supported elsewhere in the app
# (DEFAULT_UI_LANGUAGE / DEFAULT_VIDEO_LANGUAGE).
_LANGUAGE = [
    _opt("ro", "characterLookups.language.ro", "Romanian", "Română"),
    _opt("en", "characterLookups.language.en", "English", "Engleză"),
    _opt("fr", "characterLookups.language.fr", "French", "Franceză"),
    _opt("de", "characterLookups.language.de", "German", "Germană"),
    _opt("es", "characterLookups.language.es", "Spanish", "Spaniolă"),
    _opt("it", "characterLookups.language.it", "Italian", "Italiană"),
]


def build_character_lookups() -> CharacterLookupsResponse:
    return CharacterLookupsResponse(
        gender=_GENDER,
        marital_status=_MARITAL,
        education_level=_EDUCATION,
        social_status=_SOCIAL_STATUS,
        professional_seniority=_SENIORITY,
        authority_level=_AUTHORITY,
        personality_archetype=_ARCHETYPE,
        communication_style=_COMM_STYLE,
        temperament=_TEMPERAMENT,
        emotional_tone=_TONE,
        level_scale=_LEVEL_SCALE,
        conflict_style=_CONFLICT_STYLE,
        decision_style=_DECISION_STYLE,
        narrative_role=_NARRATIVE_ROLE,
        voice_gender=_VOICE_GENDER,
        voice_age=_VOICE_AGE,
        speaking_speed=_SPEAKING_SPEED,
        pitch=_PITCH,
        tone=_TONE,
        camera_framing=_CAMERA_FRAMING,
        mood=_MOOD,
        character_status=_CHARACTER_STATUS,
        image_status=_IMAGE_STATUS,
        language=_LANGUAGE,
    )

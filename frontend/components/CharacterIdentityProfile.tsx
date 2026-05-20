"use client";

// Read-only character dossier — logical chapters, each field a row rectangle
// (label left / value right). Reads the stored CharacterProfile. No editing
// here (Edit profile lives in the header / Settings tab).
import type { CharacterResponse } from "@/lib/characters";

type V = string | number | boolean | null | undefined | readonly string[];

function fmt(v: V): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
  if (typeof v === "boolean") return v ? "Da" : "Nu";
  return String(v);
}

function Row({ label, value }: { readonly label: string; readonly value: V }) {
  return (
    <div className="dossier-row">
      <span className="dossier-label">{label}</span>
      <span className="dossier-value">{fmt(value)}</span>
    </div>
  );
}

function Chapter({ title, children }: { readonly title: string; readonly children: React.ReactNode }) {
  return (
    <section className="dossier-chapter">
      <h3 className="dossier-chapter-title">{title}</h3>
      <div className="dossier-rows">{children}</div>
    </section>
  );
}

const PHYSICAL_KEYS = [
  "height", "weight_or_build", "skin_tone", "hair_color", "hair_style",
  "eye_color", "face_shape", "distinctive_features",
] as const;

export function CharacterIdentityProfile({ character }: { readonly character: CharacterResponse }) {
  const p = character.profile;
  const id = p.identity ?? {};
  const ap = p.appearance ?? {};
  const ed = p.education ?? {};
  const pe = p.personality ?? {};
  const vo = p.voice ?? {};
  const sb = p.script_behaviour ?? {};

  // Physical completeness.
  const filled = PHYSICAL_KEYS.filter((k) => {
    const val = (ap as Record<string, unknown>)[k];
    return val !== null && val !== undefined && val !== "";
  }).length;
  const completeness =
    filled <= 2 ? { label: "Insuficient", cls: "badge-danger" }
    : filled <= 4 ? { label: "Basic", cls: "badge-warn" }
    : filled <= 6 ? { label: "Bun", cls: "badge-info" }
    : { label: "Detaliat", cls: "badge-success" };

  const warnings: string[] = [];
  if (!character.main_reference_image_id) warnings.push("Lipsă referință față");
  if (!character.full_body_reference_image_id) warnings.push("Lipsă referință corp");
  if (filled <= 2) warnings.push("Profil fizic prea scurt");
  if (!ap.hair_color || !ap.eye_color) warnings.push("Lipsesc date păr/ochi");
  if (!ap.face_shape) warnings.push("Lipsește forma feței");

  return (
    <div className="dossier">
      <div className="dossier-status">
        <span>Profil fizic: <span className={`badge ${completeness.cls}`}>{completeness.label}</span>{" "}
          ({filled}/{PHYSICAL_KEYS.length})</span>
        {warnings.length > 0 && (
          <span className="dossier-warnings">
            {warnings.map((w) => <span key={w} className="badge badge-warn">⚠ {w}</span>)}
          </span>
        )}
      </div>

      <Chapter title="A. Identitate generală">
        <Row label="Nume" value={id.name} />
        <Row label="Nume afișat" value={id.display_name} />
        <Row label="Gen" value={id.gender} />
        <Row label="Vârstă aparentă" value={id.age} />
        <Row label="Data nașterii" value={id.date_of_birth} />
        <Row label="Naționalitate" value={id.nationality} />
        <Row label="Limbă nativă" value={id.native_language} />
        <Row label="Limbi vorbite" value={id.spoken_languages} />
        <Row label="Locație" value={id.current_location ?? id.place_of_birth} />
        <Row label="Ocupație" value={ed.occupation} />
        <Row label="Educație" value={ed.education_level} />
        <Row label="Status social/profesional" value={id.social_status} />
      </Chapter>

      <Chapter title="B. Rol narativ și utilitate">
        <Row label="Rol în videoclipuri" value={sb.default_role_in_videos} />
        <Row label="Stil de conținut" value={sb.prompt_style_notes} />
        <Row label="Subiecte permise" value={sb.allowed_topics} />
        <Row label="Subiecte de evitat" value={sb.blocked_topics} />
        <Row label="Expertiză" value={ed.expertise} />
      </Chapter>

      <Chapter title="C. Personalitate">
        <Row label="Arhetip" value={pe.archetype} />
        <Row label="Temperament" value={pe.temperament} />
        <Row label="Stil de comunicare" value={pe.communication_style} />
        <Row label="Ton emoțional" value={pe.emotional_tone} />
        <Row label="Nivel umor" value={pe.humor_level} />
        <Row label="Nivel încredere" value={pe.confidence_level} />
        <Row label="Nivel empatie" value={pe.empathy_level} />
        <Row label="Nivel formalitate" value={pe.formality_level} />
        <Row label="Motivații" value={pe.motivations} />
      </Chapter>

      <Chapter title="D. Voce și stil de vorbire">
        <Row label="Voce TTS" value={character.default_voice_provider_id} />
        <Row label="Gen voce" value={vo.voice_gender} />
        <Row label="Vârstă voce" value={vo.voice_age} />
        <Row label="Ritm" value={vo.speaking_speed} />
        <Row label="Înălțime (pitch)" value={vo.pitch} />
        <Row label="Ton" value={vo.tone} />
        <Row label="Accent" value={vo.accent} />
        <Row label="Limbă" value={vo.preferred_language} />
      </Chapter>

      <Chapter title="E. Aspect fizic">
        <Row label="Înălțime" value={ap.height} />
        <Row label="Constituție" value={ap.weight_or_build} />
        <Row label="Formă față" value={ap.face_shape} />
        <Row label="Ten" value={ap.skin_tone} />
        <Row label="Culoare păr" value={ap.hair_color} />
        <Row label="Stil păr" value={ap.hair_style} />
        <Row label="Culoare ochi" value={ap.eye_color} />
        <Row label="Trăsături distinctive" value={ap.distinctive_features} />
        <Row label="Note consistență vizuală" value={ap.visual_consistency_notes} />
      </Chapter>

      <Chapter title="F. Vestimentație și stil vizual">
        <Row label="Stil vestimentar" value={ap.clothing_style} />
        <Row label="Constrângeri vizuale (negative)" value={ap.negative_visual_constraints} />
        <Row label="Fundal implicit" value={sb.default_background} />
        <Row label="Încadrare implicită" value={sb.default_camera_framing} />
      </Chapter>

      <Chapter title="G. Context social și profesional">
        <Row label="Domeniu" value={ed.industry_domain} />
        <Row label="Rol curent" value={ed.current_role} />
        <Row label="Nivel autoritate" value={ed.authority_level} />
        <Row label="Note reputație" value={ed.reputation_notes} />
      </Chapter>

      <Chapter title="H. Compliance / constrângeri">
        <Row label="Persoană reală" value={id.is_real_person ?? false} />
        <Row label="Persona publică" value={id.is_public_persona ?? false} />
        <Row label="Note siguranță" value={sb.safety_notes} />
        <Row label="Referință față setată" value={!!character.main_reference_image_id} />
        <Row label="Referință corp setată" value={!!character.full_body_reference_image_id} />
      </Chapter>
    </div>
  );
}

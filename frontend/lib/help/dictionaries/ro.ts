// Phase 11A — Romanian Help corpus. Same 30 topic IDs as ``./en.ts``.

import type { HelpBlock } from "../types";
import type { HelpTopic } from "./en";

const p = (text: string): HelpBlock => ({ type: "p", text });
const h = (level: 2 | 3 | 4, text: string): HelpBlock => ({ type: "h", level, text });
const kv = (
  rows: readonly (readonly [string, string])[],
  caption?: string,
): HelpBlock => ({ type: "kv", caption, rows });
const code = (text: string, caption?: string, lang?: string): HelpBlock => ({
  type: "code",
  text,
  caption,
  lang,
});
const callout = (
  tone: "info" | "warn" | "danger" | "success",
  text: string,
  title?: string,
): HelpBlock => ({ type: "callout", tone, text, title });
const list = (items: readonly string[], ordered = false): HelpBlock => ({
  type: "list",
  items,
  ordered,
});

export const HELP_TOPICS_RO: Readonly<Record<string, HelpTopic>> = {
  dashboard: {
    id: "dashboard",
    section: "Tablou de bord",
    title: "Tablou de bord",
    summary: "Starea stack-ului, joburile recente și link-uri rapide — ecranul de start.",
    body: [
      p("Tabloul de bord sumarizează starea stack-ului și face link la fluxurile principale. Indicatorul Backend din dreapta sus interoghează /healthz, așa că știi dacă API-ul răspunde."),
      p("Tabelul cu joburi recente este o proiecție subțire a GET /api/v1/jobs ordonată după created_at. Apasă pe orice rând pentru a intra în Detaliu job."),
      list([
        "Link-urile rapide te duc la Joburi / Job nou / Încărcări / Setări.",
        "Bara de activitate din dreapta este restrânsibilă — restrânge-o pentru mai mult spațiu.",
        "Apasă ? oricând pentru a deschide acest overlay de ajutor.",
      ]),
    ],
    related: ["jobs-list", "create-job", "settings"],
  },
  "jobs-list": {
    id: "jobs-list",
    section: "Joburi",
    title: "Listă de joburi",
    summary: "Răsfoiește toate joburile, filtrează după stare, intră în detalii.",
    body: [
      p("/jobs este cuprinsul operațional. Rândurile afișează id, descriere, etapa curentă, starea, progresul și ora creării."),
      kv([
        ["Descriere", "Primele 60 de caractere ale brief-ului operatorului."],
        ["Stare", "pending_compliance / accepted / published / rejected / failed."],
        ["Etapă", "Etapa în execuție acum, sau ultima finalizată pentru joburi terminale."],
        ["Progres", "Procent etape finalizate."],
        ["Limbă", "Faza 11A — video_language al jobului (ro / en)."],
      ]),
      p("Filtrul de stare reduce tabelul fără a re-fetch-ui totul."),
    ],
    related: ["create-job", "job-detail", "recovery-controls"],
  },
  "create-job": {
    id: "create-job",
    section: "Joburi",
    title: "Creează job",
    summary: "Wizard cu file pentru un reel nou: descriere → furnizori → limbă → conformitate.",
    body: [
      p("Fiecare filă validează local înainte de a permite trecerea; nimic nu ajunge la backend până la submit."),
      kv([
        ["Descriere", "Text liber + durata țintă. Scriitorul de scenariu o folosește ca prompt."],
        ["Voce", "Alege TTS (sintetizat) sau audio furnizat (încărci mai întâi, apoi referezi)."],
        ["Furnizori", "Suprascrie valorile implicite — id-uri script / voce / video. Moștenirea implicită e ok."],
        ["Limbă + subtitrări", "Faza 11A — alege limba video; opțional activează subtitrări SRT/VTT sidecar."],
        ["Conformitate", "Două atestări obligatorii. Submit rămâne dezactivat până când ambele sunt bifate."],
      ]),
      p("Referințele de imagine / audio sunt trimise ca obiecte complete (type=local_path, path, mime_type, checksum). Formularul le construiește din artefactul selectat sub Încărcări."),
    ],
    related: ["provider-selection", "video-language", "subtitles", "uploads"],
  },
  "provider-selection": {
    id: "provider-selection",
    section: "Furnizori",
    title: "Selecție furnizori",
    summary: "Suprascriere per-job pentru script / TTS / video / audio-processor / image-processor.",
    body: [
      p("provider_selection este un JSON salvat pe rândul Job. Fiecare câmp e opțional; câmpurile lipsă moștenesc valoarea implicită."),
      kv([
        ["script_provider_id", "template (determinist) | ollama (LLM local)."],
        ["tts_provider_id", "piper | f5tts_ro | external."],
        ["video_provider_id", "sadtalker | musetalk | wav2lip | liveportrait."],
        ["audio_processor_id", "De obicei ffmpeg_convert."],
        ["image_processor_id", "De obicei stdlib_image_validation."],
      ]),
      callout("info", "Furnizori personalizați pot fi înregistrați în Setări → Furnizori personalizați (localStorage; persistență backend mai târziu)."),
    ],
    related: ["script-generation", "tts-generation", "sadtalker-video", "custom-providers"],
  },
  "script-generation": {
    id: "script-generation",
    section: "Generare",
    title: "Generare scenariu",
    summary: "Descriere → scenariu structurat. Template e determinist; Ollama e un LLM local.",
    body: [
      p("POST /api/v1/script/generate rulează furnizorul ales. Template returnează un scenariu determinist în 3 părți (hook / body / cta) și este mereu disponibil."),
      p("Ollama apelează un daemon local (implicit http://localhost:11434). Este blocat în spatele SCRIPTWRITER_ENABLE_NETWORK_CALLS=true, deci o instalare proaspătă nu face niciodată apel de rețea."),
      kv([
        ["script_provider_disabled", "Apelurile de rețea sunt dezactivate — schimbă variabila de mediu."],
        ["script_model_missing", "Rulează `ollama pull <model>` și reîncearcă."],
        ["script_provider_unreachable", "Daemonul nu răspunde sau OLLAMA_BASE_URL e greșit."],
        ["script_generation_failed", "Daemonul a răspuns dar răspunsul nu a trecut de validare."],
      ]),
    ],
    related: ["ollama", "create-job"],
  },
  "tts-generation": {
    id: "tts-generation",
    section: "Generare",
    title: "Generare TTS",
    summary: "Text → audio. Piper pentru engleză (și altele), F5TTS-Ro pentru română.",
    body: [
      p("POST /api/v1/tts/generate rulează backend-ul TTS ales și înregistrează un artefact audio (sau returnează un 503 categorisit dacă un gate nu trece)."),
      kv([
        ["tts_runtime_missing", "piper-tts / f5-tts nu sunt instalate în imagine."],
        ["tts_assets_missing", "Fișiere de voce / model lipsă pe disc."],
        ["tts_generation_failed", "Sinteza a rulat dar WAV-ul nu a trecut de validare."],
        ["tts_provider_not_configured", "Variabila de mediu (PIPER_MODELS_ROOT, F5TTS_RO_BASE_URL) nu e setată."],
        ["tts_provider_not_implemented", "Furnizorul e un placeholder."],
      ]),
    ],
    related: ["piper", "f5tts-ro", "create-job"],
  },
  "f5tts-ro": {
    id: "f5tts-ro",
    section: "Furnizori",
    title: "F5TTS-Ro (Română)",
    summary: "Wrapper opțional TTS pentru română. CPU implicit, GPU capabil.",
    body: [
      p("F5TTS-Ro este un serviciu Docker opt-in (profile=tts-ro) care înfășoară F5-TTS upstream configurat pentru română. Backend-ul rămâne fără torch; wrapper-ul face munca grea."),
      h(3, "Configurare"),
      code("make docker-tts-ro-build\nmake docker-tts-ro-up\nexport F5TTS_RO_BASE_URL=http://aivideo-model-tts-ro-1:8080", "Build, start și spune backend-ului unde să găsească serviciul.", "bash"),
      p("Pune un WAV de referință la models/tts/f5tts-ro/reference/voice.wav și setează F5TTS_RO_REFERENCE_TEXT cu transcrierea acestuia."),
    ],
    related: ["tts-generation", "provider-selection", "model-assets"],
  },
  piper: {
    id: "piper",
    section: "Furnizori",
    title: "Piper (TTS local)",
    summary: "TTS implicit pentru engleză. Prietenos cu CPU, rapid, fără rețea.",
    body: [
      p("Piper este motorul TTS implicit. Instalează-l recompilând backend-ul cu INSTALL_PIPER=true, apoi pune fișierele de voce (.onnx + .onnx.json) sub PIPER_MODELS_ROOT."),
      code("INSTALL_PIPER=true make docker-light-build\nmake docker-light-up\n# Pune voci sub models/tts/piper/<voce>/<voce>.onnx + .onnx.json", undefined, "bash"),
    ],
    related: ["tts-generation", "model-assets"],
  },
  ollama: {
    id: "ollama",
    section: "Furnizori",
    title: "Ollama (LLM scenariu)",
    summary: "LLM local pentru scriere de scenariu via daemon HTTP Ollama. Apel de rețea opt-in.",
    body: [
      p("Ollama este singurul furnizor de scenariu care face apel de rețea — la daemonul tău Ollama (implicit http://localhost:11434). Setează SCRIPTWRITER_ENABLE_NETWORK_CALLS=true și OLLAMA_BASE_URL pe backend pentru a activa."),
      kv([
        ["OLLAMA_BASE_URL", "Unde caută backend-ul daemonul."],
        ["SCRIPTWRITER_OLLAMA_MODEL", "Numele modelului, ex. qwen2.5:7b."],
        ["SCRIPTWRITER_ENABLE_NETWORK_CALLS", "Comutator hard. Implicit false."],
      ]),
    ],
    related: ["script-generation", "errors-glossary"],
  },
  "sadtalker-video": {
    id: "sadtalker-video",
    section: "Furnizori",
    title: "Video SadTalker",
    summary: "Generare reală MP4 cu lip-sync pe serviciul wrapper GPU.",
    body: [
      p("SadTalker este furnizorul video v1 implicit. Rulează într-un serviciu Docker dedicat (profile=sadtalker, port 8062). Backend-ul light proxează /api/v1/video/generate la wrapper prin HTTP."),
      h(3, "Cerințe"),
      list([
        "NVIDIA driver + NVIDIA Container Toolkit pe host.",
        "GPU cu ≥6 GB VRAM.",
        "Cinci fișiere de greutăți sub models/lipsync/sadtalker/{checkpoints,gfpgan}/ (~2 GB total).",
        "SADTALKER_BASE_URL=http://aivideo-model-sadtalker-1:8080 pe backend.",
      ]),
      callout("info", "Faza Demo-RO-1 corectează problema cross-uid: backend + orchestrator fac chmod 0o777 pe subdir-ul per-job astfel încât wrapper-ul (uid 10002) să poată muta MP4-ul.", "Permisiuni automate"),
    ],
    related: ["gpu-runtime", "model-assets", "video-language"],
  },
  subtitles: {
    id: "subtitles",
    section: "Media",
    title: "Subtitrări",
    summary: "Subtitrări SRT / VTT sidecar generate din scenariu. Burn-in neimplementat.",
    body: [
      p("Faza 11A adaugă generare opt-in de subtitrări sidecar. Activează `Generează subtitrări` în formularul Creează job și alege una sau mai multe limbi; backend-ul scrie .srt sau .vtt pentru fiecare limbă sub /storage/artifacts/subtitles/<job_id>/."),
      kv([
        ["subtitle_enabled", "Comutator master, salvat pe rândul Job."],
        ["subtitle_languages", "Listă de coduri de limbă. Default automat la [video_language] când e activ dar listă goală."],
        ["subtitle_format", "srt sau vtt."],
        ["subtitle_burn_in", "Captat pe rând; execuția burn-in NU e implementată — fișierele rămân sidecar."],
      ]),
      callout("warn", "Cue-urile sunt distribuite uniform pe target_duration_seconds. Metadata spune alignment=approximate / real_timing=false. Alinierea forțată reală este muncă viitoare.", "Sincronizare aproximativă"),
    ],
    related: ["video-language", "artifacts", "create-job"],
  },
  "video-language": {
    id: "video-language",
    section: "Media",
    title: "Limba video",
    summary: "Limba vorbită a reel-ului. Salvată pe Job; afectează default-urile de subtitrări.",
    body: [
      p("Alege limba vorbită sub `Limbă și subtitrări` din Creează job. Astăzi ro/en sunt cetățeni de primă clasă; alte coduri eșuează la validarea de schemă."),
      list([
        "Română (ro): asociază cu F5TTS-Ro pentru voce sintetizată. WAV / MP3 furnizat funcționează și el.",
        "Engleză (en): asociază cu Piper.",
      ]),
      p("video_language apare în lista sumar Job, în Detaliu job și în metadata final_export."),
    ],
    related: ["subtitles", "f5tts-ro", "piper", "settings"],
  },
  uploads: {
    id: "uploads",
    section: "Încărcări",
    title: "Încărcări",
    summary: "Lasă text, audio sau imagini. Fiecare devine o referință de artefact reutilizabilă.",
    body: [
      p("Încărcările sunt artefacte de clasa întâi — primesc sha256, un id stabil și trăiesc în volumul artifacts_data alături de output-urile generate. Mai multe joburi pot referi aceeași referință."),
      kv([
        ["Text", "Text simplu (UTF-8). Folosit ca override de scenariu sau sidecar."],
        ["Audio", "audio/wav (PCM). MP3 / M4A convertite automat prin ffmpeg server-side."],
        ["Imagine", "image/png, image/jpeg. Minim 256×256 pentru detectorul de față SadTalker; 1024×1024 ideal."],
      ]),
    ],
    related: ["audio-upload", "image-upload"],
  },
  "audio-upload": {
    id: "audio-upload",
    section: "Încărcări",
    title: "Încărcare audio",
    summary: "WAV obligatoriu, MP3 / M4A convertite automat server-side prin ffmpeg.",
    body: [
      kv([
        ["Format nativ", "audio/wav, PCM, 16 / 22.05 / 44.1 / 48 kHz, mono sau stereo."],
        ["Conversie automată", "audio/mpeg, audio/mp4 trecute prin ffmpeg → WAV mono la sample rate original."],
        ["Durată minimă", "1 s (validată de audio_validation)."],
        ["Durată maximă", "AUDIO_MAX_DURATION_SECONDS (implicit 600 s)."],
      ]),
      callout("warn", "Asigură-te că curl trimite MIME-ul corect (`-F 'file=@x.wav;type=audio/wav'`) — application/octet-stream e respins.", "Indicii MIME"),
    ],
    related: ["uploads", "create-job"],
  },
  "image-upload": {
    id: "image-upload",
    section: "Încărcări",
    title: "Încărcare imagine",
    summary: "Portrete PNG / JPEG. Dimensiunile minime contează pentru detectorul de față.",
    body: [
      kv([
        ["MIME permis", "image/png, image/jpeg."],
        ["Dimensiuni minime", "256×256 pentru SadTalker; ideal 1024×1024 portret cu fața centrată."],
        ["Dimensiune maximă fișier", "UPLOAD_IMAGE_MAX_BYTES (implicit 20 MB)."],
      ]),
      callout("info", "thispersondoesnotexist.com produce fețe AI CC0 care trec atestarea de persoană sintetică.", "Surse de persoane sintetice"),
    ],
    related: ["uploads", "create-job"],
  },
  "job-detail": {
    id: "job-detail",
    section: "Joburi",
    title: "Detaliu job",
    summary: "Totul despre un job: cronologie, artefacte, conformitate, QC, export, recuperare.",
    body: [
      p("Pagina de detaliu este sursa unică de adevăr pentru un reel. Este compusă din carduri stivuite, fiecare actualizabil independent."),
      kv([
        ["Antet", "Descriere, stare, durată țintă, modul voce / față, butoane editare / anulare / reîncercare."],
        ["Cronologia etapelor", "Toate cele 10 etape DAG cu starea, durata și motivul respingerii dacă este cazul."],
        ["Tabel artefacte", "Fiecare artefact înregistrat al jobului cu tip / dimensiune / durată / dimensiuni / link descărcare."],
        ["Previzualizare video / audio", "Inline <video> / <audio> pentru artefacte binare."],
        ["Evenimente conformitate", "Fiecare accept / reject cu timestamp + motiv."],
        ["Raport QC", "Încredere lip-sync, prezență watermark, stare disclosure AI."],
        ["Card export final", "Publicat vs blocat, metadata disclosure AI, stare semnare C2PA."],
        ["Comenzi recuperare", "Reset, retry from stage, sau cancel."],
      ]),
    ],
    related: ["artifacts", "qc-report", "final-export", "recovery-controls"],
  },
  artifacts: {
    id: "artifacts",
    section: "Joburi",
    title: "Artefacte",
    summary: "Fiecare output al unei etape este un artefact tipat cu sha256.",
    body: [
      kv([
        ["script", "JSON. Scenariu structurat (hook / body / cta / language)."],
        ["audio", "Fișier WAV pe disc."],
        ["image", "PNG / JPEG pe disc."],
        ["video", "MP4 pe disc."],
        ["subtitle", "SRT sau VTT pe disc. metadata_summary conține language_code + format."],
        ["edit_plan / metadata / qc_report / final_export", "JSON inline."],
      ]),
      p("Artefactele binare sunt accesibile via GET /api/v1/artifacts/<id>/content. Adaugă ?download=true pentru un header attachment."),
    ],
    related: ["real-vs-metadata", "subtitles"],
  },
  "real-vs-metadata": {
    id: "real-vs-metadata",
    section: "Joburi",
    title: "Real vs metadate",
    summary: "Unele artefacte conțin bytes reali; altele sunt placeholder-uri pentru teste.",
    body: [
      p("Fazele 1–6 demo au produs artefacte doar metadate: un checksum + dimensiune, dar bytes-ii erau stub. Faza 10B+ produce MP4-uri reale când wrapper-ul SadTalker e activ."),
      list([
        "MP4 real: metadata_summary.phase=phase10b_sadtalker_via_wrapper, dimensiune în sute de KB.",
        "MP4 stub: fișier sub 200 bytes, metadata_summary.phase=phase2_noop.",
        "Tabelul Artefacte afișează mereu numărul de bytes — 376 KB e real; 64 bytes e placeholder.",
      ]),
    ],
    related: ["artifacts", "sadtalker-video"],
  },
  "qc-report": {
    id: "qc-report",
    section: "Joburi",
    title: "Raport QC",
    summary: "Încredere lip-sync + watermark + disclosure AI.",
    body: [
      p("Etapa QC produce un raport JSON care punctează reel-ul în trei verificări. Detaliul job-ului îl afișează ca un card cu badge colorat (pass / warn / fail)."),
      kv([
        ["lipsync_confidence", "Scor 0.0–1.0. Prag în jurul 0.7 astăzi."],
        ["watermark_present", "boolean — overlay-ul a fost detectat?"],
        ["disclosure_present", "boolean — metadata disclosure AI este prezentă?"],
        ["decision", "pass | warn | fail."],
      ]),
      callout("info", "POST /api/v1/qc/inspect poate re-rula QC pe un artefact video existent fără a re-rula întregul DAG.", "Re-rulare QC"),
    ],
    related: ["job-detail", "final-export", "errors-glossary"],
  },
  "final-export": {
    id: "final-export",
    section: "Joburi",
    title: "Export final",
    summary: "Pachet publisher. Inserează disclosure AI, semnează cu C2PA când e necesar.",
    body: [
      p("Etapa publisher produce un artefact final_export care sumarizează reel-ul publicat — URI output, dimensiune, sha256, stare watermark + C2PA și metadata disclosure AI."),
      kv([
        ["status", "published | blocked | skipped."],
        ["disclosure_status", "embedded | missing | pending."],
        ["watermark_required / c2pa_required", "Ecou al atestărilor operatorului."],
        ["export_uri", "URI on-disk final."],
      ]),
      p("POST /api/v1/export/finalize poate re-rula pachetul publisher pentru un artefact video existent."),
    ],
    related: ["qc-report", "subtitles", "artifacts"],
  },
  "recovery-controls": {
    id: "recovery-controls",
    section: "Joburi",
    title: "Comenzi de recuperare",
    summary: "Reîncearcă, resetează, anulează — fără a pierde artefactele anterioare.",
    body: [
      kv([
        ["Reîncearcă de la etapa…", "Alege cea mai timpurie etapă de refăcut. Artefactele anterioare rămân atașate."],
        ["Resetează la compliance", "Setează starea înapoi la pending_compliance, șterge toate stage_run-urile. Inputurile rămân."],
        ["Anulează", "Terminal — setează status=failed cu reason=operator_cancelled."],
      ]),
      callout("warn", "Reset / retry nu șterg niciodată artefactele de pe disc — doar le dezleagă de stage_run-ul activ."),
    ],
    related: ["job-detail", "errors-glossary", "edit-job", "retry-job", "failed-job-recovery"],
  },
  "edit-job": {
    id: "edit-job",
    section: "Joburi",
    title: "Editează un job existent",
    summary: "Modifică descrierea, furnizorii, scenariul, limba sau subtitrările înainte de a reîncerca pipeline-ul.",
    body: [
      p("Pagina Editare (link în lista de joburi și în header-ul detaliilor de job) îți permite să corectezi metadatele unui job existent fără a crea unul nou. Faza 11B lărgește suprafața editabilă astfel încât joburile respinse / eșuate să poată fi reparate."),
      kv([
        ["Descriere / durată țintă", "Editabile mereu până când jobul este publicat."],
        ["Text scenariu", "Editabil cât timp jobul este pending_compliance, respins sau eșuat."],
        ["Mod voce / față", "La fel ca textul scenariului — comută la ``provided_audio`` dacă TTS-ul nu funcționează în mediul tău."],
        ["Selecția furnizorilor", "Editează pe categorii (scenariu / TTS / video / audio / imagine). Gol înseamnă „moștenește valorile implicite”."],
        ["Limbă + subtitrări", "Editează video_language, subtitle_enabled, lista de limbi, formatul, burn-in."],
        ["Flag-uri watermark / C2PA", "Legate de conformitate — trebuie să rămână true."],
      ]),
      callout("info", "Editarea unui job respins / eșuat NU îl reîncearcă automat. După salvare, apasă Reîncearcă pe aceeași pagină (sau pe Detalii job). Workerul preia metadatele noi la următorul ciclu."),
      callout("warn", "Furnizorii custom_future_* (ex. ``custom_future_tts``) sunt simple placeholdere de metadate. Dacă un job este respins cu ``tts_provider_not_configured``, comută la un furnizor implementat (``piper`` sau ``f5tts_ro``) și reîncearcă."),
    ],
    related: ["retry-job", "failed-job-recovery", "provider-selection", "job-detail", "create-job"],
  },
  "retry-job": {
    id: "retry-job",
    section: "Joburi",
    title: "Reîncearcă după editare",
    summary: "Re-pune în coadă un job eșuat / respins ca workerul să re-ruleze DAG-ul cu metadatele actualizate.",
    body: [
      p("Reîncercarea este activă atunci când jobul este în starea ``rejected`` sau ``failed``. POST /api/v1/jobs/{id}/retry comută starea înapoi la pending_compliance, șterge motivul anterior al respingerii, iar workerul orchestratorului preia rândul la următoarea iterație."),
      list([
        "Istoria etapelor se păstrează — rândurile vechi de stage_run rămân pentru audit.",
        "retry_count și retry_requested_at se salvează în recovery_metadata.",
        "Editează mai întâi furnizorul / descrierea / scenariul, apoi apasă Reîncearcă. Noul ciclu folosește valorile actualizate.",
      ]),
      callout("warn", "Dacă apeși Reîncearcă fără să corectezi cauza (ex. tot ``custom_future_tts``), noua rulare va fi respinsă pentru același motiv."),
    ],
    related: ["edit-job", "failed-job-recovery", "recovery-controls"],
  },
  "failed-job-recovery": {
    id: "failed-job-recovery",
    section: "Joburi",
    title: "Recuperează un job eșuat / respins",
    summary: "Rețetă end-to-end: diagnosticare motiv, editare câmp incorect, reîncercare.",
    body: [
      p("Când un job ajunge la ``rejected`` sau ``failed``, pagina Detalii job afișează rejection_reason și are link spre cronologie ca să vezi etapa care a eșuat."),
      list([
        "Deschide pagina Detalii job și citește rejection_reason (ex. ``tts_provider_not_configured: only 'piper' is wired``).",
        "Apasă Editează jobul. Formularul preîncarcă selecția curentă, descrierea, scenariul, limba.",
        "Modifică câmpul incorect — ex. tts_provider_id de la ``custom_future_tts`` la ``piper``.",
        "Salvează modificările — dashboard-ul confirmă ``Modificările au fost salvate``.",
        "Apasă Reîncearcă după editare (sau folosește secțiunea Recovery controls din Detalii job). Workerul re-rulează DAG-ul.",
      ]),
      callout("info", "Folosește ``voice_mode=provided_audio`` plus un artefact audio deja încărcat dacă vrei să sari complet peste TTS în pasul de recuperare."),
    ],
    related: ["edit-job", "retry-job", "errors-glossary"],
  },
  settings: {
    id: "settings",
    section: "Setări",
    title: "Setări",
    summary: "Valori implicite la nivel de deploy, furnizori personalizați, preferințe UI.",
    body: [
      kv([
        ["URL API backend", "Unde vorbește dashboard-ul. Util pentru backend-uri remote."],
        ["Limba interfeței", "ro / en. Persistă în rândul DB operator_settings + localStorage."],
        ["Limba video implicită", "Folosită ca valoare inițială la creare de joburi noi."],
        ["Interval polling", "Cât de des dashboard-ul re-fetch-uiește /jobs și /summary."],
        ["Furnizori impliciți", "Id-uri script / TTS / video implicite."],
        ["Furnizori personalizați", "Înregistrează propriile id-uri (localStorage; viitor: tabel backend)."],
      ]),
    ],
    related: ["docker-ports", "custom-providers", "provider-diagnostics"],
  },
  "docker-ports": {
    id: "docker-ports",
    section: "Setări",
    title: "Porturi Docker",
    summary: "Mapare alt-port pentru backend / frontend / postgres / redis.",
    body: [
      p("Compose-ul dev mapează implicit backend → :8001, frontend → :3010, postgres → :5433, redis → :6380 ca stack-ul să poată coexista cu un alt mediu dev local."),
      code(
        "BACKEND_PORT=8001 FRONTEND_PORT=3010 POSTGRES_PORT=5433 REDIS_PORT=6380 \\\n  NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 \\\n  docker compose -f docker/compose.dev.yml up -d",
        "Copiază asta din Setări → Porturi Docker.",
        "bash",
      ),
    ],
    related: ["settings"],
  },
  "provider-diagnostics": {
    id: "provider-diagnostics",
    section: "Setări",
    title: "Diagnoză furnizori (Test1)",
    summary: "Probe live de readiness + generare dry-run din bara dreaptă.",
    body: [
      p("Tab-ul Test1 din bara dreaptă afișează /api/v1/providers/<categorie> live + îți permite să faci o rulare one-off cu payload de stoc. Nu se creează niciun job."),
      kv([
        ["Test (script)", "POST /api/v1/script/generate cu un brief fix."],
        ["Test (tts)", "POST /api/v1/tts/generate cu o singură propoziție."],
        ["Test (video)", "Nu e încă wired — folosește /jobs/new pentru video real."],
      ]),
    ],
    related: ["provider-selection", "errors-glossary"],
  },
  logs: {
    id: "logs",
    section: "Setări",
    title: "Panou loguri",
    summary: "Bus de loguri frontend. Local sesiunii — dispare la refresh.",
    body: [
      p("Panoul Loguri înregistrează doar evenimente frontend: poll-uri eșuate, erori API, confirmări de acțiuni, schimbări de setări."),
      list([
        "Export JSON / TXT descarcă intrările vizibile.",
        "Clear golește bus-ul.",
        "Nu există persistență backend pentru loguri astăzi — logurile dispar la refresh-ul browserului.",
      ]),
    ],
    related: ["provider-diagnostics"],
  },
  "custom-providers": {
    id: "custom-providers",
    section: "Setări",
    title: "Furnizori personalizați",
    summary: "Înregistrează propriile id-uri de furnizor care indică spre un endpoint HTTP local.",
    body: [
      p("Furnizorii personalizați îți permit să cablezi un LLM privat, un TTS self-hosted sau un API video extern în dashboard fără rebuild backend."),
      p("Configurația trăiește în localStorage (per browser). Persistența multi-operator necesită un tabel backend viitor."),
    ],
    related: ["provider-selection"],
  },
  "errors-glossary": {
    id: "errors-glossary",
    section: "Referință",
    title: "Glosar de erori",
    summary: "Fiecare error_code pe care API-ul îl poate returna, plus ce rezolvă fiecare.",
    body: [
      kv([
        ["script_provider_disabled", "SCRIPTWRITER_ENABLE_NETWORK_CALLS=true pentru activare."],
        ["script_model_missing", "`ollama pull <model>` și reîncearcă."],
        ["script_provider_unreachable", "Daemon down sau OLLAMA_BASE_URL greșit."],
        ["tts_runtime_missing", "Instalează piper-tts (rebuild cu INSTALL_PIPER=true) sau pornește F5TTS-Ro."],
        ["tts_assets_missing", "Pune fișiere de voce / model sub rădăcina configurată."],
        ["tts_generation_failed", "WAV-ul a eșuat la validare; verifică sample rate / channels."],
        ["video_assets_missing", "5 fișiere de greutăți SadTalker lipsă pe disc."],
        ["video_gpu_missing", "Driver / Container Toolkit neînregistrate."],
        ["video_runtime_missing", "Folosește wrapper-ul GPU, nu backend-ul light."],
        ["provider_not_implemented", "Schimbă backend-ul sau așteaptă furnizorul să fie livrat."],
        ["provider_not_configured", "Variabilă de mediu nesetată."],
      ]),
    ],
    related: ["script-generation", "tts-generation", "sadtalker-video", "recovery-controls"],
  },
  "gpu-runtime": {
    id: "gpu-runtime",
    section: "Infrastructură",
    title: "Runtime GPU",
    summary: "Driver, NVIDIA Container Toolkit, capcane Blackwell.",
    body: [
      list([
        "`nvidia-smi` trebuie să listeze cel puțin un dispozitiv. Dacă spune no devices, verifică `lspci -nnk -d 10de:` întâi — GPU-ul poate fi suspendat pe un laptop Optimus.",
        "`docker run --rm --gpus all nvidia/cuda:12.4.1-runtime-ubuntu22.04 nvidia-smi` trebuie să reușească.",
        "Blackwell (RTX 50) necesită driverul open-kernel-module (ex. nvidia-driver-595-open).",
      ]),
      callout("warn", "Faza 10B a confirmat: torch ≥ 2.7 cu wheels cu128 e necesar pentru sm_120; torch mai vechi crashează cu `no kernel image is available`.", "Versiune torch pentru Blackwell"),
    ],
    related: ["sadtalker-video", "model-assets"],
  },
  "model-assets": {
    id: "model-assets",
    section: "Infrastructură",
    title: "Active de model",
    summary: "Unde trăiesc greutățile, cum se instalează și politica fără auto-download.",
    body: [
      kv([
        ["SadTalker", "models/lipsync/sadtalker/{checkpoints,gfpgan}/ (5 fișiere, ~2 GB)."],
        ["Piper", "models/tts/piper/<voce>/<voce>.onnx + .onnx.json."],
        ["F5TTS-Ro", "models/tts/f5tts-ro/ + voce de referință la models/tts/f5tts-ro/reference/voice.wav."],
        ["GFPGAN", "models/lipsync/sadtalker/gfpgan/GFPGANv1.4.pth (333 MB)."],
      ]),
      callout("warn", "ALLOW_MODEL_AUTODOWNLOAD=false este pin-uit. Backend-ul nu descarcă niciodată greutăți la build sau primul run; le pui manual.", "Fără auto-download"),
    ],
    related: ["sadtalker-video", "piper", "f5tts-ro"],
  },
  "demo-jobs": {
    id: "demo-jobs",
    section: "Referință",
    title: "Joburi demo",
    summary: "Scenarii pre-secționate care exersează fiecare cale de furnizor.",
    body: [
      p("`make scenario-jobs` și `make demo-jobs` secționează două matrice complementare de joburi — vezi docs/runbooks/scenario-jobs.md. Faza Demo-RO-1 a adăugat un set curat cu temă românească (Demo RO — …) acoperind turism, fabrică, educație, brutărie, conversie MP3, F5TTS-Ro, furnizori personalizați și un job SadTalker MP4 real."),
      list([
        "Re-rularea seeder-ului demo este idempotentă — adaugă, nu duplică.",
        "Joburile demo nu rulează API-uri plătite și nu trag automat greutăți.",
      ]),
    ],
    related: ["jobs-list", "create-job"],
  },
};

export const HELP_TOPIC_IDS_RO: readonly string[] = Object.keys(HELP_TOPICS_RO);

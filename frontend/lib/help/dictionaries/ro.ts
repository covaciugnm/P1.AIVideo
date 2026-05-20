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
    section: "Navigație",
    title: "Tabul „Tablou de bord” a fost eliminat",
    summary: "Phase 21 — / redirecționează la Personaje. Flow-ul este Personaje → Video-uri.",
    body: [
      p("Începând cu Phase 21 tabul „Tablou de bord” a fost scos din navigație pentru că duplica integral lista de Video-uri. Calea / redirecționează acum direct la /characters (Personaje) — pagina de start naturală a fluxului."),
      p("Fluxul operatorului devine:"),
      list([
        "1. Personaje — creează / alegi personajul cu care vrei să generezi video-ul.",
        "2. Video-uri — vezi lista istorică + apeși „+ Video nou” pentru a începe.",
        "3. Detaliu video — urmărești progresul DAG, descarci MP4-ul final, ștergi dacă vrei.",
      ]),
      p("Indicatorul Backend din header continuă să apară pe TOATE paginile; cardul cu Backend Logs e tot în sidebar dreapta. Doar landing-ul dedicat dispare."),
    ],
    related: ["characters", "jobs-list", "create-job"],
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
  "video-types": {
    id: "video-types",
    section: "Video-uri",
    title: "Tipuri de video (talking_head / scenes_only / news_presenter)",
    summary: "Trei pipeline-uri distincte pentru videoclipuri. Phase 21.",
    body: [
      p("Începând cu Phase 21 fiecare video are un tip explicit care decide pipeline-ul backend și forma formularului de creare."),
      kv([
        ["talking_head", "Pipeline-ul clasic (11 etape). Un singur portret static al personajului cu gura sincronizată pe scenariul rostit. Cel mai rapid (~2-3 min/video)."],
        ["scenes_only", "B-roll multi-scenă (6 etape). Niciun personaj pe ecran. Operatorul (sau LLM-ul) propune o listă de scene cu prompt FLUX + text rostit; fiecare scenă devine un clip cu Ken-Burns + voiceover, ffmpeg le concatenează. ~4-6 min."],
        ["news_presenter", "Hibrid (9 etape). Segmente prezentator (lipsync SadTalker pe portretul personajului) intercalate cu scene B-roll. Necesită personaj. ~5-10 min în funcție de cât e SadTalker."],
      ]),
      p("La submit operatorul alege tipul în Step 0 al formularului; restul cardurilor se adaptează (scenes_only ascunde secțiunea Față, talking_head ascunde editorul de plan de scene)."),
      list([
        "Toate cele trei tipuri trec prin aceleași etape de QC + export disclosure + publisher, deci auditul rămâne uniform.",
        "Pipeline YAML-urile sunt în pipelines/ — reel_default.yaml (talking_head), reel_scenes_only.yaml, reel_news_presenter.yaml.",
        "Stage-ul comun scene_composer (Phase 21) este single-process pentru toate scenele dintr-un video; nu paralelizează scene între ele.",
      ]),
    ],
    related: ["create-job", "scene-plan", "subtitles", "characters"],
  },
  "scene-plan": {
    id: "scene-plan",
    section: "Video-uri",
    title: "Plan de scene (scenes_only / news_presenter)",
    summary: "Editor de scene cu cards add/delete/reorder; LLM propune lista, operatorul ajustează.",
    body: [
      p("Pentru tipurile scenes_only și news_presenter, după ce introduci descrierea apeși „Generează plan scene”. LLM-ul (Ollama Qwen3.6 implicit) propune 3–8 scene cu:"),
      kv([
        ["scene_number", "Index 1-based, refăcut automat dacă reordonezi."],
        ["kind", "„presenter” (lipsync pe portret) sau „broll” (imagine FLUX statică cu zoom). scenes_only forțează kind=broll."],
        ["spoken_text", "Ce rostește vocea în această scenă, în limba aleasă pentru video."],
        ["visual_description", "Prompt FLUX în engleză — doar pentru broll. Background + lumină + stil. Fără oameni, fără branduri reale."],
        ["duration_s", "Între 1.0 și 20.0 secunde. Suma trebuie să fie în ±20% față de target_duration_seconds."],
      ]),
      p("Fiecare card e editabil — schimbi kind, modifici textul, ajustezi durata, reordonezi cu săgeți, ștergi sau adaugi scene. Butonul Submit validează ca toate scenele să aibă spoken_text non-empty și ca broll să aibă visual_description."),
    ],
    related: ["video-types", "create-job", "subtitles"],
  },
  "video-orientation": {
    id: "video-orientation",
    section: "Video-uri",
    title: "Format video (portret / peisaj / pătrat)",
    summary: "Selector de orientare pentru video-uri mobile (9:16) sau clasice (16:9). Phase 22.",
    body: [
      p("La crearea unui video alegi formatul de ieșire din selectorul de orientare (Step 0, sub tipul de video). Se aplică tuturor celor trei tipuri de video."),
      kv([
        ["Peisaj (16:9)", "Format clasic widescreen 1280×720. Implicit. Pentru YouTube orizontal, prezentari."],
        ["Portret (9:16)", "Format mobil vertical 720×1280. Pentru TikTok, Instagram Reels, YouTube Shorts."],
        ["Pătrat (1:1)", "Format 1024×1024. Potrivit pentru postări in feed Instagram/Facebook."],
      ]),
      p("Tehnic: scene_composer randează imaginile FLUX direct la dimensiunile țintă, iar clipurile SadTalker (pătrate) sunt scalate + completate cu margini negre (scale-fit + pad) pentru a se potrivi formatului ales. Toate clipurile sunt normalizate la aceleași dimensiuni inainte de concatenarea ffmpeg."),
      p("Interfata web este responsive: pe telefon meniul se rearanjeaza, formularele devin pe o coloana, iar tabelele se pot derula orizontal."),
    ],
    related: ["create-job", "video-types", "scene-plan"],
  },
  "create-job": {
    id: "create-job",
    section: "Video-uri",
    title: "Creează video",
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
    summary: "TTS real în română folosind cdorob/f5-tts-romanian pe un wrapper GPU/CPU opt-in.",
    body: [
      p("F5TTS-Ro este un serviciu Docker opt-in (profile=tts-ro) care înfășoară F5-TTS upstream cu fine-tune-ul românesc cdorob/f5-tts-romanian. Imaginea light a backend-ului rămâne fără torch; wrapper-ul face munca grea ML."),
      h(3, "Model: cdorob/f5-tts-romanian"),
      kv([
        ["Repo HF", "huggingface.co/cdorob/f5-tts-romanian"],
        ["Licență", "MIT"],
        ["Model de bază", "F5TTS_v1_Base (SWivid/F5-TTS upstream)"],
        ["Date antrenament", "Common Voice 17 RO (35k mostre) + datadriven-company/TTS-Romanian (50k mostre), ~173h total"],
        ["Fișiere", "model_last.pt (5.4 GB) + vocab.txt (~14 KB)"],
        ["Tokenizer", "bazat pe caractere"],
      ]),
      h(3, "Active obligatorii furnizate de operator"),
      list([
        "models/tts/f5tts-ro/model/model_last.pt — checkpoint-ul cdorob (descărcat via huggingface_hub, vezi runbook).",
        "models/tts/f5tts-ro/model/vocab.txt — livrat în același repo HF.",
        "models/tts/f5tts-ro/reference/voice.wav — WAV românesc curat, 3–15 secunde, un singur vorbitor.",
        "models/tts/f5tts-ro/reference/reference.txt — transcrierea exactă a WAV-ului de referință (F5-TTS o folosește pentru aliniere voice-cloning).",
      ]),
      h(3, "Configurare"),
      code("# 1. descarcă modelul (~5.4 GB, licență MIT, fără auth)\nhuggingface-cli download cdorob/f5-tts-romanian --local-dir models/tts/f5tts-ro/model\n\n# 2. plasează un WAV românesc sintetic de referință + transcrierea exactă\nls models/tts/f5tts-ro/reference/voice.wav models/tts/f5tts-ro/reference/reference.txt\n\n# 3. build + start wrapper (stratul ML greu este opt-in via INSTALL_F5TTS=true, implicit true)\nmake docker-tts-ro-build\nmake docker-tts-ro-up\n\n# 4. spune-i backend-ului unde se află wrapper-ul\nexport F5TTS_RO_BASE_URL=http://aivideo-model-tts-ro-1:8080", "Active furnizate de operator + pornire serviciu. Fără auto-download cu excepția invocării explicite a huggingface_hub.", "bash"),
      callout("info", "Când să alegi F5TTS-Ro vs Piper: F5TTS-Ro produce audio românesc de calitate superioară (voce clonată din WAV-ul tău de referință) dar costă ~80–120 secunde per cerere pe CPU (mai rapid pe GPU). Piper este ~1 secundă per cerere și e alegerea implicită potrivită pentru scenarii scurte sau dezvoltare cu latență mică.", "Compromis de performanță"),
      callout("warn", "Imaginea wrapper-ului include torch + f5-tts (~2 GB creștere imagine). Construiește cu --build-arg INSTALL_F5TTS=false pentru un wrapper doar-/health onest care raportează mereu runtime_missing.", "Dimensiune imagine"),
    ],
    related: ["tts-generation", "provider-selection", "model-assets", "piper"],
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
    summary: "LLM local extern. Nu este instalat în containerul backend — operatorul rulează daemonul Ollama separat.",
    body: [
      p("Ollama este un serviciu LLM local extern. Nu este instalat în containerul backend. Pentru a-l folosi, instalează/rulează Ollama separat, descarcă modelul configurat, setează OLLAMA_BASE_URL și activează SCRIPTWRITER_ENABLE_NETWORK_CALLS=true. Dacă nu este disponibil, folosește providerul Template."),
      h(3, "Semantica stărilor"),
      kv([
        ["Instalat", "Nu — Ollama este un serviciu extern pe host/container."],
        ["Configurat", "Parțial — prin OLLAMA_BASE_URL (implicit http://host.docker.internal:11434 din compose, http://localhost:11434 din shell-ul host)."],
        ["Funcțional", "Doar dacă SCRIPTWRITER_ENABLE_NETWORK_CALLS=true ȘI daemonul e accesibil ȘI modelul configurat e descărcat."],
        ["Fallback", "Dacă Ollama e dezactivat sau inaccesibil, aplicația folosește providerul Template (scenariu determinist / static)."],
      ]),
      h(3, "Configurare"),
      code("# 1. Instalează Ollama pe host (sau rulează-l într-un container vecin)\ncurl -fsSL https://ollama.com/install.sh | sh\nollama serve\n\n# 2. Descarcă modelul (operator-explicit — nu se descarcă automat)\nollama pull qwen2.5:7b\n\n# 3. Spune-i backend-ului unde se află daemonul + activează poarta de rețea\nexport OLLAMA_BASE_URL=http://host.docker.internal:11434\nexport OLLAMA_MODEL=qwen2.5:7b\nexport SCRIPTWRITER_ENABLE_NETWORK_CALLS=true\n\n# 4. Restart backend + verifică\ndocker compose -f docker/compose.dev.yml up -d backend\ncurl -fsS http://localhost:8001/api/v1/providers/llm | jq '.[] | select(.provider_id==\"ollama\")'", "Pornește un daemon Ollama extern și conectează backend-ul la el. Înlocuiește qwen2.5:7b cu modelul preferat (qwen3.6 este implicitul proiectului).", "bash"),
      h(3, "Coduri de eroare"),
      kv([
        ["script_provider_disabled", "SCRIPTWRITER_ENABLE_NETWORK_CALLS=false. Activează-l și repornește."],
        ["script_provider_unreachable", "OLLAMA_BASE_URL nu duce nicăieri. Verifică `ollama serve` și accesibilitatea din containerul backend."],
        ["script_model_missing", "Daemonul e accesibil dar modelul configurat nu e descărcat. Rulează `ollama pull <model>` pe hostul Ollama."],
        ["script_generation_failed", "Daemonul a răspuns dar răspunsul a fost malformat. Verifică logurile daemonului."],
      ]),
      callout("warn", "Aplicația NU rulează niciodată `ollama pull` automat. Makefile-ul expune `make ollama-status` / `make ollama-models` / `make ollama-smoke` pentru diagnostic; niciun target nu descarcă modele fără confirmarea operatorului.", "Fără auto-pull"),
    ],
    related: ["script-generation", "errors-glossary", "provider-selection"],
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
      h(3, "Cerințe pentru portret"),
      p("SadTalker rulează un detector de față + extractor de repere pe imaginea sursă înainte de a putea anima un cap care vorbește. Detectorul este strict; este necesar un portret frontal recognoscibil."),
      list([
        "O singură față umană vizibilă — fotografiile de grup, corpuri întregi sau fundaluri goale eșuează.",
        "Frontal sau aproape frontal — pozele strict din profil nu pot fi decupate.",
        "Lumină bună — siluetele, imaginile foarte întunecate sau foarte palide eșuează.",
        "Fără ocluzii puternice — ochelarii de soare, măștile, mâinile peste față, părul care acoperă fața afectează detectarea reperelor.",
        "Dimensiune minimă 256×256, recomandat ≥512×512 (verificarea de potrivire respinge orice e mai mic).",
        "PNG / JPEG / WebP, decodate de OpenCV-ul wrapper-ului.",
        "Doar persoană sintetică — flag-urile operator-consent + synthetic_person sunt obligatorii conform politicii de conformitate.",
      ]),
      h(3, "Coduri de eroare categorizate"),
      kv([
        ["video_face_landmark_missing", "Cropper-ul SadTalker nu a găsit o față în imaginea sursă. Încarcă un portret frontal mai clar și reîncearcă. Jobul rămâne în 'rejected' deci PATCH + retry funcționează."],
        ["video_face_image_too_small", "Imaginea este <256×256. Verificarea de potrivire din backend o respinge înainte de a invoca SadTalker."],
        ["video_assets_missing", "Unul dintre cele cinci fișiere de greutăți obligatorii nu se află sub SADTALKER_MODELS_ROOT."],
        ["video_gpu_missing", "torch nu vede un dispozitiv CUDA. Verifică `nvidia-smi` și flag-ul --gpus all al containerului."],
        ["video_runtime_missing", "Imaginea wrapper-ului nu are torch / opencv / sursa SadTalker — operatorul trebuie să reconstruiască."],
        ["video_generation_failed", "Coș de gunoi: SadTalker s-a închis non-zero fără o semnătură recunoscută. Verifică panoul de diagnostic pentru tail-ul subprocesului."],
      ]),
    ],
    related: ["gpu-runtime", "model-assets", "video-language", "image-upload", "failed-job-recovery"],
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
  localization: {
    id: "localization",
    section: "Referință",
    title: "Localizare (i18n)",
    summary:
      "Regula de paritate UI RO/EN, structura dicționarelor, helperul de formatare.",
    body: [
      p("Faza 11A a introdus dicționarele duale EN/RO, iar Faza 11A-FIX a finalizat curățarea: fiecare șir vizibil operatorului trăiește în `frontend/lib/i18n/dictionaries/{en,ro}.ts`, fiecare topic de Help în `frontend/lib/help/dictionaries/{en,ro}.ts`, iar enumerările runtime trec prin `frontend/lib/i18n/formatters.ts` (tStatus, tStage, tArtifactType, …), astfel încât dashboard-ul nu mai afișează niciodată `pending_compliance` sau `tts_provider_not_configured` în formă brută."),
      kv([
        ["t(path, params)", "Caută o cheie din dicționar. Parametrii înlocuiesc placeholderele `{name}`. Cheile lipsă cad pe engleză, apoi pe calea brută."],
        ["formatRelativeLocalized(t, iso)", "Timp relativ bilingv. Înlocuiește `formatRelative`-ul englezesc pentru orice valoare afișată operatorului."],
        ["localizeApiDetail(t, err)", "Mapează fragmente cunoscute de erori Pydantic / FastAPI la chei din dicționar (persoană sintetică, consimțământ, intervalul duratei, câmp interzis, …) și cade pe textul brut englezesc doar pentru forme necunoscute."],
        ["tStatus / tStage / tArtifactType / tVoiceMode / tFaceMode / tProviderStatus", "Helpere tipizate enum-la-etichetă. Pasează mereu `t` din `useT()`."],
      ]),
      callout(
        "info",
        "Regulă permanentă: fiecare etichetă / buton / eroare / stare / etapă / tip de artefact / topic de Help nou trebuie să actualizeze AMBELE dicționare în același PR. Testele din Faza 11A-FIX impun paritatea cheilor și caută engleză hardcodată în JSX.",
        "Regulă de mentenanță",
      ),
      list([
        "Engleză permisă în JSX: ID-uri de furnizori, căi API, verbe HTTP, formate de fișiere (WAV/MP3/PNG/JPEG/MP4/SRT/VTT), nume de variabile de mediu, nume de modele, stack trace-uri brute în meta-logurile.",
        "Folosește `useT()` chiar și în componentele client cu o singură etichetă — e gratuit.",
        "Când o valoare de dicționar ar fi identică pe ambele limbi (ex. `MP4`), păstrează identitatea — testul strict de paritate exclude lista albă tehnică.",
      ]),
    ],
    related: ["settings", "errors-glossary"],
  },
  // -----------------------------------------------------------------
  // Phase 12 — Personaje
  // -----------------------------------------------------------------
  characters: {
    id: "characters",
    section: "Personaje",
    title: "Tabul Personaje",
    summary:
      "Personaje reutilizabile cu identitate, aspect, personalitate, voce + bibliotecă de imagini.",
    body: [
      p(
        "Tabul Personaje gestionează personaje reutilizabile pe care le poți atașa videoclipurilor. Fiecare personaj are un profil structurat (identitate, aspect, educație, personalitate, voce, comportament în script) pe care scriptwriter-ul, generatorul de imagini și TTS-ul îl citesc la momentul submit al jobului.",
      ),
      h(3, "Comportament la editare & ștergere"),
      list([
        "Personajele sunt editabile — fiecare salvare incrementează numărul de versiune și adaugă un rând în character_versions pentru traiectoria de snapshot-uri.",
        "Ștergerea este SOFT (setează deleted_at), așa că job-urile care făceau referință la personaj se rezolvă în continuare.",
        "Videoclipurile generate vechi păstrează un snapshot înghețat pe jobs.character_snapshot — editări / ștergeri NU rescriu istoricul.",
        "Generările viitoare folosesc întotdeauna versiunea curentă, editată.",
      ]),
      h(3, "Dropdown-uri standardizate"),
      p(
        "Fiecare câmp standardizat (gen, stare civilă, nivel de educație, arhetip, stil de comunicare, ton, etc.) își ia opțiunile din /api/v1/characters/lookups. Etichetele sunt traductibile prin hook-ul useT(), așa că RO / EN urmează limba globală fără rebuild.",
      ),
      callout(
        "info",
        "Când apare un provider nou (Ollama / F5-TTS / FLUX / SD3.5), apare automat în dropdown-urile relevante — fără modificări de frontend. Indicatoarele de status (verde / galben / roșu) reflectă /api/v1/providers în timp real.",
        "Registry dinamic de providers",
      ),
    ],
    related: ["character-image-library", "character-image-provider", "video-character"],
  },
  "character-image-library": {
    id: "character-image-library",
    section: "Personaje",
    title: "Biblioteca de imagini",
    summary:
      "Flux generare / acceptare / referință per personaj.",
    body: [
      p(
        "Fiecare personaj are propria bibliotecă de imagini. Generezi dintr-un prompt, accepți rezultatul, apoi promovezi o imagine acceptată ca referință principală. După ce există o referință principală, provider-ele care suportă image-to-image (FLUX BFL, Stability ultra, Replicate FLUX, fal.ai, Midjourney proxy, Recraft) o pot folosi pentru a menține personajul consistent între generări.",
      ),
      h(3, "Statusuri"),
      kv([
        ["draft", "Proaspăt generată — încă necurată."],
        ["accepted", "Operator a aprobat — eligibilă să devină referință principală."],
        ["rejected", "Operator a marcat ca necorespunzătoare — păstrată pentru istoric."],
        ["reference", "Promovată ca referință principală (una singură per personaj)."],
        ["archived", "Ascunsă din vizualizările default; nu este ștearsă."],
      ]),
    ],
    related: ["character-image-provider", "characters", "character-main-reference"],
  },
  "character-image-provider": {
    id: "character-image-provider",
    section: "Personaje",
    title: "Provider-i de generare imagini",
    summary:
      "FLUX local (default) + FLUX BFL API + SD3.5 + 13 alți backend-i cu indicatoare de status.",
    body: [
      p(
        "Categoria image_generator listează 16 backend-i. Doar provider-ul mock rulează fără setări — restul ridică o eroare categorisită `provider_not_configured` / `runtime_missing` până configurezi env vars sau construiești containerul wrapper.",
      ),
      h(3, "Wrappere GPU locale (oglinda model-sadtalker)"),
      kv([
        ["flux_local", "FLUX.1-schnell / dev. Setează FLUX_LOCAL_BASE_URL + FLUX_LOCAL_MODELS_ROOT."],
        ["sd35_local", "Stable Diffusion 3.5 Large. SD35_LOCAL_BASE_URL + SD35_LOCAL_MODELS_ROOT."],
        ["sdxl_local", "Alternativă cu VRAM mai mic. SDXL_LOCAL_BASE_URL."],
        ["comfyui_local", "Adu-ți propriul workflow JSON. COMFYUI_BASE_URL."],
        ["a1111_local", "AUTOMATIC1111 webui /sdapi/v1. A1111_BASE_URL."],
      ]),
      h(3, "API-uri hosted (doar API key în env)"),
      kv([
        ["flux_bfl_api", "Cloud Black Forest Labs. FLUX_BFL_API_KEY."],
        ["stability_api", "SD3.5 hosted. STABILITY_API_KEY."],
        ["replicate_api", "Multi-model. REPLICATE_API_TOKEN."],
        ["fal_api", "Hosting low-latency. FAL_KEY."],
        ["together_api", "FLUX + community. TOGETHER_API_KEY."],
        ["openai_dalle3", "DALL·E 3. Refolosește OPENAI_API_KEY."],
        ["ideogram_api", "IDEOGRAM_API_KEY."],
        ["recraft_api", "RECRAFT_API_KEY."],
        ["vertex_imagen3", "Google Imagen 3. VERTEX_AI_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS."],
        ["midjourney_unofficial", "Proxy Discord-bot fragil. MIDJOURNEY_PROXY_URL + MIDJOURNEY_PROXY_TOKEN."],
      ]),
      callout(
        "warn",
        "Apelurile API outbound necesită IMAGE_GENERATOR_ENABLE_NETWORK_CALLS=true. Credențialele singure NU sunt suficiente ca să factureze automat un API.",
        "Poarta network",
      ),
    ],
    related: ["character-image-library", "providers-overview"],
  },
  "character-main-reference": {
    id: "character-main-reference",
    section: "Personaje",
    title: "Imagine de referință principală",
    summary:
      "O imagine curată per personaj pe care generările următoare o pot refolosi pentru condiționare image-to-image.",
    body: [
      p(
        "Promovează orice imagine acceptată cu `Setează ca referință principală`. Provider-ele care anunță reference_image=true în capabilities pot primi calea fișierului la apelurile ulterioare de generate.",
      ),
    ],
    related: ["character-image-library", "character-image-provider"],
  },
  "video-character": {
    id: "video-character",
    section: "Job nou",
    title: "Personaj pe formularul de video",
    summary:
      "Dropdown-ul Personaj injectează profilul în job. Snapshot-ul se îngheață la submit.",
    body: [
      p(
        "Alege un personaj pentru a forwarda identitatea / limba / rolul / provider-ul de voce / referința de imagine în acest job. Profilul complet se face snapshot pe jobs.character_snapshot la submit — editări sau ștergeri ulterioare ale personajului NU rescriu acest job.",
      ),
    ],
    related: ["characters", "character-image-library"],
  },
  "character-gender": {
    id: "character-gender",
    section: "Personaje",
    title: "Câmp Gen",
    summary: "Dropdown standardizat din /api/v1/characters/lookups.",
    body: [
      p(
        "Folosit de constructorii de prompt-uri (script + imagine) pentru a menține personajul consistent. Valorile se mapează la etichete traductibile via cheile characterLookups.gender.*.",
      ),
    ],
  },
  "character-dob": {
    id: "character-dob",
    section: "Personaje",
    title: "Data nașterii & vârstă",
    summary: "Vârsta se calculează din DOB la citire; suprascriere directă posibilă.",
    body: [
      p(
        "Introdu data nașterii prin date picker. CharacterProfile.computed_age() întoarce vârsta derivată în ani. Dacă preferi să nu setezi DOB, completează direct câmpul `Vârstă`.",
      ),
    ],
  },
  "character-spoken-languages": {
    id: "character-spoken-languages",
    section: "Personaje",
    title: "Limbi vorbite",
    summary: "Listă comma-separated de coduri de limbă pe care le poate vorbi personajul.",
    body: [
      p(
        "Scriptwriter-ul folosește această listă pentru a constrânge limba(le) dialogului. Combinată cu `voice.preferred_language` pentru a alege vocea TTS.",
      ),
    ],
  },
  "character-education": {
    id: "character-education",
    section: "Personaje",
    title: "Nivel de educație",
    summary: "Influențează registrul vocabularului în script.",
    body: [
      p(
        "Valoarea standardizată (PhD, Master, Licență, ...) este inclusă în contextul de prompt al scriptului ca LLM-ul să potrivească registrul.",
      ),
    ],
  },
  "character-archetype": {
    id: "character-archetype",
    section: "Personaje",
    title: "Arhetip de personalitate",
    summary:
      "Arhetip la nivel înalt combinat cu ton + valori.",
    body: [
      p(
        "Se combină cu stilul de comunicare, temperamentul și tonul într-un briefing format paragraf pe care scriptwriter-ul îl citește prin /api/v1/characters/:id/script-context.",
      ),
    ],
  },
  "character-comm-style": {
    id: "character-comm-style",
    section: "Personaje",
    title: "Stil de comunicare",
    summary: "Formal, informal, conversațional, autoritar, persuasiv, …",
    body: [
      p(
        "Setează cât de formal / jucăuș / autoritar sună discursul sintetizat. Se combină cu câmpul `ton` pentru profilul final al vocii.",
      ),
    ],
  },
  "character-tts-provider": {
    id: "character-tts-provider",
    section: "Personaje",
    title: "Provider TTS preferat",
    summary:
      "Setează default-ul provider-ului de voce pentru orice video nou legat de acest personaj.",
    body: [
      p(
        "Operatorul poate suprascrie per-job. Dropdown-ul listează fiecare provider din /api/v1/providers/tts cu un indicator de status (verde = gata, galben = configurat dar nesondat, roșu = indisponibil).",
      ),
    ],
  },
  "character-blocked-topics": {
    id: "character-blocked-topics",
    section: "Personaje",
    title: "Subiecte interzise",
    summary:
      "Guard-rails de subiecte pe care scriptwriter-ul le primește explicit și refuză să le treacă.",
    body: [
      p(
        "Listă comma-separated. Inclusă în blocul de context al scriptului sub `## Safety & topic guard rails` ca LLM-ul să le vadă in-prompt.",
      ),
    ],
  },
  "providers-overview": {
    id: "providers-overview",
    section: "Providers",
    title: "Registry dinamic de providers",
    summary:
      "Fiecare dropdown citește din /api/v1/providers — adăugarea unui provider nu necesită rebuild de frontend.",
    body: [
      p(
        "Faza 12 a adăugat indicatoarele de status dinamice (verde / galben / roșu). Provider-i noi apar automat în dropdown-uri odată ce sunt listați în registry. Indicatorul de status reflectă starea env-based + ultima probă de health-check (POST /api/v1/providers/:category/:id/health-check).",
      ),
      callout(
        "info",
        "Suprascrierile operatorului stau în tabelul DB feature_providers. Flag enabled, display order și ultimul status de health sunt mergeite peste registry-ul de cod la momentul request-ului — util pentru a dezactiva un provider fragil fără redeploy.",
        "Suprascrieri de operator",
      ),
    ],
  },
  // -----------------------------------------------------------------
  // Phase 12X — Tab Keys din right-sidebar
  // -----------------------------------------------------------------
  "api-keys": {
    id: "api-keys",
    section: "Setări",
    title: "Chei API & Endpoint-uri (right-sidebar)",
    summary:
      "Depozit persistent de secrete în Postgres. Valorile se încarcă în os.environ la pornirea backend-ului deci supraviețuiesc restart-urilor Docker.",
    body: [
      p(
        "Deschide tab-ul Keys din right-sidebar pentru a adăuga / vedea / testa credențiale pentru fiecare provider hosted (FLUX BFL, Stability, Replicate, fal.ai, Together, OpenAI, Ideogram, Recraft, Vertex Imagen, Midjourney proxy) + URL-urile wrapper-elor locale (FLUX, SDXL, SD3.5, ComfyUI, A1111, SadTalker, F5TTS-Ro, Ollama).",
      ),
      h(3, "Cum funcționează"),
      list([
        "Fiecare Save face POST /api/v1/secrets/ → persistat în tabelul api_secrets (Postgres).",
        "Hook-ul lifespan al backend-ului încarcă fiecare rând în os.environ la startup — adaptorii care citesc env vars îl preiau fără cod.",
        "Butonul Test rulează o probă de reachability ieftină per tip credențial (ex: GET /api/whoami-v2 pentru HF_TOKEN, GET /v1/models pentru OpenAI).",
        "Rezultatul persistă pe api_secrets.last_test_status; punctul verde/roșu din UI reflectă ultimul outcome al testului.",
        "La cererea operatorului, valoarea e vizibilă în clar (nu mascată).",
      ]),
      h(3, "Endpoint-uri"),
      kv([
        ["GET /api/v1/secrets", "Listă toate secretele persistate + catalogul de 24 chei cunoscute."],
        ["POST /api/v1/secrets", "Upsert după key_name. Împinge valoarea în os.environ imediat."],
        ["PUT /api/v1/secrets/{key_name}", "Update valoarea unui secret existent."],
        ["DELETE /api/v1/secrets/{key_name}", "Soft-remove + drop din os.environ."],
        ["POST /api/v1/secrets/{key_name}/test", "Rulează proba per-cheie."],
      ]),
      callout(
        "info",
        "Adaptorii hosted necesită suplimentar IMAGE_GENERATOR_ENABLE_NETWORK_CALLS=true (setabil tot din Keys tab) înainte să facă apeluri HTTP outbound. Oglinda poartă SCRIPTWRITER_ENABLE_NETWORK_CALLS.",
        "Poartă network",
      ),
    ],
    related: ["providers-overview", "character-image-provider"],
  },
  // -----------------------------------------------------------------
  // Phase 12W — Wrapper-e Docker GPU pentru image generators
  // -----------------------------------------------------------------
  "image-wrappers-docker": {
    id: "image-wrappers-docker",
    section: "Providers",
    title: "Wrappere GPU locale (Docker)",
    summary:
      "5 image generators rulează ca containere Docker sibling — FLUX, SDXL, SD3.5, ComfyUI, A1111 (status variabil).",
    body: [
      p(
        "Faza 12W a adăugat docker/model-flux, model-sdxl, model-sd35, model-comfyui, model-a1111. Oglinda pattern-ului model-sadtalker + model-tts-ro: bază CUDA + server FastAPI + mount read-only models/. Adaptorul backend face POST request de generate, wrapper-ul scrie PNG-ul în volumul artifacts partajat.",
      ),
      h(3, "Comenzi lifecycle"),
      kv([
        ["make docker-flux-build / -up / -down / -logs / -smoke", "FLUX.1-schnell pe portul 8064."],
        ["make docker-sdxl-build / -up / ...", "Stable Diffusion XL pe portul 8063."],
        ["make docker-sd35-build / -up / ...", "Stable Diffusion 3.5 Large pe portul 8065."],
        ["make docker-comfyui-build / -up / ...", "Workflow runner ComfyUI pe portul 8066."],
        ["make docker-a1111-build / -up / ...", "AUTOMATIC1111 WebUI pe portul 8067."],
      ]),
      h(3, "Management VRAM"),
      list([
        "FLUX-schnell + SDXL + SD3.5 consumă fiecare 10–22 GB VRAM în inferență (cu CPU offload). Rulează unul singur odată pe GPU de 24 GB.",
        "ComfyUI / A1111 țin modelul în VRAM idle — oprește-le între provider-i dacă schimbi modelul.",
        "Toate wrapper-ele folosesc torch 2.7+cu128 compatibil Blackwell pentru RTX 5090 (sm_120).",
      ]),
      callout(
        "warn",
        "Image-ul A1111 e construit dar runtime-ul depinde de repo-ul arhivat Stability-AI/stablediffusion + cod ldm SD2-era. Substitutul CompVis pe care l-am vendorat acoperă op-urile SD1; căile SD2 (modelul de depth, modurile attention MMDiT) crash la primul import. Tratează wrapper-ul a1111 ca 'image preparat, runtime necesită patch de operator' până când se cabla un fork SD2 cunoscut bun.",
        "Notă A1111",
      ),
    ],
    related: ["sadtalker-video", "character-image-provider"],
  },
  "video-pipeline": {
    id: "video-pipeline",
    section: "Video",
    title: "Pipeline job video (Personaje → SadTalker)",
    summary:
      "Flux end-to-end: audio F5TTS + imagine portret + snapshot personaj → DAG orchestrator → MP4 SadTalker.",
    body: [
      p(
        "Submit-ul unui video folosește POST /api/v1/jobs/from-inputs cu audio_artifact_id + image_artifact_id + character_id. Orchestratorul rulează DAG-ul canonic (policy_gate → scriptwriter → voice → face → identity_guard → pre_lipsync_auth → lipsync → editor → qc → publisher → export_disclosure_validation). SadTalker generează MP4 în stage-ul lipsync și artifact-ul e înregistrat pe job.",
      ),
      h(3, "Input-uri"),
      list([
        "Audio — WAV generat de F5TTS-Ro la /storage/inputs/audio (sau încărcat de operator). voice_mode=provided_audio.",
        "Față — portret încărcat la /storage/inputs/images. face_mode=provided_image.",
        "character_id (opțional) — backend face snapshot al profilului personajului pe jobs.character_snapshot la momentul submit, deci editări viitoare nu rescriu istoricul. Tabelul character_videos primește un rând de link.",
      ]),
      h(3, "Ce e persistat"),
      list([
        "Rând jobs (lifecycle-ul canonic al jobului).",
        "Link character_videos (job_id ↔ character_id).",
        "Rând artifacts pointând la /storage/artifacts/video/{job_id}/sadtalker_*.mp4.",
        "compliance_events + stage_runs pentru audit trail complet.",
      ]),
      callout(
        "info",
        "Bugfix Faza 12W: containerele agent-* (scriptwriter / editor / qc / publisher / compliance) nu aveau mount-urile /storage deci voice stage eșua cu 'audio file not found'. Compose montează acum inputs_data + artifacts_data + ../models pe fiecare agent.",
        "Fix mount storage",
      ),
    ],
    related: ["video-character", "sadtalker-video", "characters"],
  },
  // -----------------------------------------------------------------
  // Faza 12T — Pagina Ajutor tehnic
  // -----------------------------------------------------------------
  "technical-help": {
    id: "technical-help",
    section: "Referință",
    title: "Pagina Ajutor tehnic",
    summary:
      "Randare live a docs/TECHNICAL_ARCHITECTURE.md servit de backend; căutare full-text, cuprins și descărcare Markdown.",
    body: [
      p(
        "Se deschide din meniul „Tehnic” sau la /technical-help. Pagina apelează GET /api/v1/system/technical-architecture și randează Markdown-ul cu un câmp de căutare lipit sus. Potrivirile sunt evidențiate în paragrafe, liste, tabele și blocuri de cod; cuprinsul urmărește titlurile de nivel 1 și 2.",
      ),
      h(3, "Endpoint-uri"),
      kv([
        ["GET /api/v1/system/technical-architecture", "JSON: title, source_path, size_bytes, markdown, generated_at."],
        ["GET /api/v1/system/technical-architecture.md", "Markdown brut (text/markdown) folosit de butonul Descarcă."],
      ]),
      h(3, "De ce trăiește pe disc"),
      list([
        "Sursa oficială este docs/TECHNICAL_ARCHITECTURE.md, versionat în repo.",
        "Dockerfile-ul backend-ului îl copiază în /app/docs/ ca să poată fi citit fără mount runtime.",
        "Modificările intră live la următorul build al imaginii backend — fără migrare DB.",
      ]),
      callout(
        "info",
        "Folosește caseta de căutare pentru rezolvări rapide: nume de provider, porturi, variabile de mediu, revizii Alembic, tabele DB. Cuprinsul se ascunde cât timp există filtru activ.",
        "Sfaturi căutare",
      ),
    ],
    related: ["api-keys", "providers-overview", "video-pipeline"],
  },
};

export const HELP_TOPIC_IDS_RO: readonly string[] = Object.keys(HELP_TOPICS_RO);

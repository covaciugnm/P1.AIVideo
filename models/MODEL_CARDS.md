# Model Cards

One section per model. **Each entry must be filled in before the corresponding model is used.** CI fails if a provider's `required_assets()` references a hash not present here.

Template for each entry:

```markdown
## <model name>

- **Repo / source URL:**
- **Version / commit:**
- **License:**
- **Commercial use OK:** yes / no / with-restrictions (cite clause)
- **Required files & sha256:**
  - `path/file1` — `sha256:...`
  - `path/file2` — `sha256:...`
- **Notes:** any restrictions, attribution requirements, or known issues.
```

---

## Llama-3.1-8B-Instruct (LLM — Scriptwriter default)

- **Repo / source URL:** TBD (Meta release page)
- **Version / commit:** TBD
- **License:** Llama Community License — review acceptable-use clauses before commercial use.
- **Commercial use OK:** with-restrictions (read license)
- **Required files & sha256:** TBD at integration time.
- **Notes:** Served via vLLM. Alternative: Qwen2.5-7B-Instruct (Apache-2.0) — preferred if Llama license posture changes.

---

## Piper voices (TTS default)

- **Repo / source URL:** <https://github.com/rhasspy/piper>
- **Version / commit:** TBD
- **License:** MIT (engine) + per-voice licenses (check each voice).
- **Commercial use OK:** depends on voice
- **Required files & sha256:** TBD per selected voice.
- **Notes:** Only ship voices whose underlying training data permits commercial synthetic use.

---

## XTTS-v2 (TTS optional)

- **Repo / source URL:** <https://github.com/coqui-ai/TTS>
- **Version / commit:** TBD
- **License:** Coqui Public Model License (CPML) — review carefully; non-commercial in some contexts.
- **Commercial use OK:** with-restrictions
- **Required files & sha256:** TBD
- **Notes:** Reference-audio cloning path is **stripped at build time** in this project regardless of upstream support.

---

## SDXL base + persona LoRA (Face)

- **Repo / source URL:** Stability AI SDXL release page; LoRA produced in-house.
- **License:** SDXL — Stability community/commercial license (read clauses). LoRA — produced in-house from licensed synthetic-face dataset.
- **Commercial use OK:** with-restrictions
- **Required files & sha256:** TBD
- **Notes:** Persona LoRA training data must be retained and license-tracked.

---

## SadTalker (LipSync — v1 default)

- **Repo / source URL:** <https://github.com/OpenTalker/SadTalker>
- **Version / commit:** TBD at integration
- **License:** Apache-2.0 (verify at integration time)
- **Commercial use OK:** yes (subject to license verification)
- **Required files & sha256:** TBD
  - `lipsync/sadtalker/checkpoints/mapping_00109-model.pth.tar`
  - `lipsync/sadtalker/checkpoints/mapping_00229-model.pth.tar`
  - `lipsync/sadtalker/checkpoints/SadTalker_V0.0.2_256.safetensors`
  - `lipsync/sadtalker/checkpoints/SadTalker_V0.0.2_512.safetensors`
  - `lipsync/sadtalker/gfpgan/GFPGANv1.4.pth`
- **Notes:** GFPGAN restoration adds ~2× wall time but improves face sharpness.

---

## MuseTalk (LipSync — v2 placeholder)

- **Repo / source URL:** <https://github.com/TMElyralab/MuseTalk>
- **License:** TBD — verify before enabling.
- **Status:** placeholder; not used in v1.

---

## Wav2Lip + GFPGAN (LipSync — fallback placeholder)

- **Repo / source URL:** <https://github.com/Rudrabha/Wav2Lip>
- **License:** Wav2Lip original checkpoints have **non-commercial** terms. Do NOT ship for commercial use without an alternative permissive checkpoint.
- **Status:** placeholder; not used in v1.

---

## WhisperX (alignment / subtitles)

- **Repo / source URL:** <https://github.com/m-bain/whisperX>
- **License:** BSD-2-Clause (Whisper itself is MIT)
- **Commercial use OK:** yes

---

## NudeNet / safety classifier

- **Repo / source URL:** <https://github.com/notAI-tech/NudeNet>
- **License:** AGPL-3.0 — check compatibility for your deployment.

---

## Public-figures embedding index (identity guard)

- **Source dataset:** in-house, derived from licensed photography dataset (record license in deployment docs).
- **Format:** FAISS / hnswlib index of CLIP embeddings.
- **Refresh:** quarterly.
- **Notes:** Stores embeddings only, not source images.

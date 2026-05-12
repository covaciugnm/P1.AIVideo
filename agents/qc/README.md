# QC Agent

Decides pass/fail on `reel_draft.mp4` with a structured report.

**Status:** to be implemented in Phase 6.

## Checks performed

| Group | Check | Implementation |
|---|---|---|
| Technical | container/codec, resolution, fps, duration | `ffprobe` |
| Audio | LUFS, true-peak, silence ratio | `pyloudnorm` |
| Visual | face present ≥ 95% frames, stability | `mediapipe` / dlib |
| NSFW | NudeNet + safety classifier | per-frame sample |
| Sync | SyncNet-style score | dedicated model |
| Subtitles | sub-to-audio drift < 80 ms | re-align with Whisper |
| Content | script vs transcript semantic diff | LLM-based |
| Content | banned-topic re-scan | policy classifier |
| Overlay | OCR finds disclosure text | tesseract |
| Identity | sampled frames vs public-figures index | CLIP NN |
| Provenance | C2PA manifest verifies | `c2patool verify` |

## Outputs

- `qc_report.json`:
  ```json
  {
    "result": "pass" | "fail",
    "findings": [
      { "check": "sync.syncnet", "result": "pass", "score": 0.82 },
      { "check": "overlay.ocr",  "result": "pass", "found": "AI-generated" }
    ],
    "remediation": [
      { "stage": "lipsync", "reason": "..." }   // present only on fail
    ]
  }
  ```

## Authority

- Can request regeneration of specific upstream stages with a reason.
- Two consecutive failures escalate to a human review queue.

## KPIs

- False-pass rate < 1% on the curated test set in `tests/fixtures/qc/`.

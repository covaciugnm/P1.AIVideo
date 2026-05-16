# Final Export — Phase 8B Real ffmpeg Packaging

This runbook covers the Phase 8B final-export surface: turning a real
video artifact (typically from Phase 7D's SadTalker output) into a
clean, downloadable MP4 stored as an `ArtifactType.final_export` row.

> **Phase 8B does not burn in a watermark, does not sign with C2PA,
> and does not publish externally.** It packages the bytes; disclosure
> work is still pending. The resulting artifact carries
> `watermark_status="pending"`, `c2pa_status="pending"`, and
> `disclosure_status="pending"` so downstream tooling knows real
> disclosure isn't done yet.

## 1. Prerequisites

- `ffmpeg` + `ffprobe` on PATH. Both are already installed in the
  light backend image (`docker/backend/Dockerfile`) since Phase 4F.
- A source video artifact with `artifact_type=video` and a `local_path`
  pointing at a real MP4 under `ARTIFACTS_LOCAL_ROOT` (or one of the
  upload roots).
- For audio mux: an audio artifact with `artifact_type=audio` and a
  `local_path` under the same allowed-roots set.

No GPU required. No model weights. No torch. No internet.

## 2. Trigger the export

```bash
# Without audio mux — fast remux into a clean MP4 container.
curl -X POST http://localhost:8000/api/v1/export/finalize \
  -H "Content-Type: application/json" \
  -d '{
        "job_id": "<job-uuid>",
        "video_artifact_id": "<video-artifact-uuid-optional>",
        "watermark_required": true,
        "c2pa_required": true
      }'

# With audio mux — replace the source's audio stream with a separate
# audio artifact's contents.
curl -X POST http://localhost:8000/api/v1/export/finalize \
  -H "Content-Type: application/json" \
  -d '{
        "job_id": "<job-uuid>",
        "video_artifact_id": "<video-uuid>",
        "audio_artifact_id": "<audio-uuid>"
      }'
```

If `video_artifact_id` is omitted, the endpoint picks the **most
recent** video artifact for the job.

## 3. Successful response

```json
{
  "status": "completed",
  "job_id": "...",
  "final_export_artifact_id": "<uuid>",
  "output_uri": "file:///storage/artifacts/final_export/<job>/final_<rand>.mp4",
  "size_bytes": 524288,
  "duration_seconds": 1.04,
  "width": 64,
  "height": 64,
  "checksum_sha256": "...",
  "message": "final export MP4 written and registered (no watermark / no C2PA yet).",
  "metadata": {
    "ffmpeg": {
      "container_format": "mov,mp4,m4a,3gp,3g2,mj2",
      "video_codec": "h264",
      "audio_codec": "aac",
      "video_stream_present": true,
      "audio_stream_present": true
    },
    "disclosure_status": "pending",
    "watermark_status": "pending",
    "c2pa_status": "pending"
  }
}
```

The registered artifact is immediately downloadable via the existing
Phase 8A endpoint:

```bash
# Preview (inline)
curl http://localhost:8000/api/v1/artifacts/<final-export-uuid>/content -o preview.mp4

# Download (attachment)
curl http://localhost:8000/api/v1/artifacts/<final-export-uuid>/content?download=true -o final.mp4
```

## 4. Categorised error codes

The endpoint always returns HTTP 200 with a structured `status` +
`error_code` (except for unknown job, which is HTTP 404). Operators
and the frontend pattern-match on `error_code`:

| `error_code` | When it fires | What to fix |
|---|---|---|
| `video_artifact_missing` | Job has no video artifact and no explicit id was passed. | Run `/api/v1/video/generate` first (Phase 7D) or pass `video_artifact_id`. |
| `video_artifact_not_found` | Explicit id doesn't match any artifact row. | Check the id. |
| `wrong_video_artifact_type` | Id points to an audio / image / etc. artifact. | Pass a `video` artifact id. |
| `video_artifact_no_local_path` | DB row exists but has no on-disk file (Phase 6A metadata stub, deleted file, etc.). | Re-run video generation. |
| `source_outside_allowed_roots` | DB row points outside `ARTIFACTS_LOCAL_ROOT` / upload roots. | Investigate — should not happen for artifacts created by the system. |
| `ffmpeg_missing` | `ffmpeg` not on PATH in the backend image. | Rebuild the image (light backend installs it by default). |
| `ffprobe_missing` | `ffmpeg` succeeded but `ffprobe` is missing — limited metadata. | Install `ffprobe` (same package). |
| `export_failed` | `ffmpeg` returned non-zero or timed out (300s cap). Partial output cleaned. | Check the truncated stderr in the `message` field. |
| `export_invalid` | `ffmpeg` returned 0 but produced empty file or no video stream. Output cleaned. | Source video probably broken; re-generate. |

The `message` field carries a single-line cause; never the full ffmpeg
stderr (which can include operator paths).

## 5. Safety contract

- `subprocess.run` is called with an argv `list`, never a shell string.
- 300-second wall-clock timeout per export run.
- Output path is server-chosen (`final_<uuid>.mp4` under
  `ARTIFACTS_LOCAL_ROOT/final_export/<job_id>/`) — operators don't
  control filenames.
- Source paths are resolved with `strict=True` and verified to live
  under one of `UPLOAD_AUDIO_ROOT` / `UPLOAD_IMAGE_ROOT` /
  `UPLOAD_TEXT_ROOT` / `ARTIFACTS_LOCAL_ROOT`. Outside-roots = 403.
- On `ffmpeg` non-zero / timeout / `OSError`, the partial output is
  unlinked and **no** artifact row is registered.
- ffprobe runs after export to validate the output exists, has bytes,
  and has a video stream. Empty / video-less output → cleanup +
  `export_invalid`.

## 6. What this phase does **not** do

- No watermark burn-in (Phase 8B records `watermark_status="pending"`).
- No C2PA signing (Phase 8B records `c2pa_status="pending"`).
- No social / external publishing.
- No re-encode by default — the cheap `-c copy` remux path keeps quality
  identical to the source. (When `audio_artifact_id` is passed we use
  `-c:v copy -c:a aac` so audio is re-encoded into MP4-friendly AAC.)
- No DAG orchestration — `/api/v1/export/finalize` is
  operator-triggered. The Phase 3J publisher stage still emits its
  JSON manifest separately; the two artifacts coexist.

## 7. Test coverage

`make phase8b-test` runs 12 invariants. Highlights:

- 404 on unknown job; categorised codes on missing / wrong-type /
  no-local-path / outside-roots video inputs.
- `ffmpeg_missing` short-circuit (monkey-patched).
- Partial cleanup verified: on simulated `ffmpeg` failure no phantom
  artifact row is registered and no leftover files remain under the
  output directory.
- Real export success path (skipped unless ffmpeg + ffprobe are on
  PATH): the registered `final_export` artifact streams over the
  Phase 8A `/api/v1/artifacts/<id>/content` endpoint as `video/mp4`,
  and `?download=true` works.
- The Phase 3J publisher handler is unchanged ("metadata-only"
  invariant pinned by a content grep).

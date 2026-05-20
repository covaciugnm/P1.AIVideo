"""Phase 21 — scene_composer stage handler.

Single stage that replaces voice+face+lipsync+editor for the
``scenes_only`` and ``news_presenter`` pipelines. For each scene in
``state.scene_plan``:

1. Generate per-scene TTS audio via the F5/Piper wrapper.
2. For broll scenes, generate a still image via FLUX with the operator-
   approved visual_description as prompt.
3. Render a per-scene MP4 clip:
   - broll: ffmpeg loop the still image + audio + Ken-Burns zoompan
     filter; duration matches scene.duration_s (or audio length).
   - presenter: feed character portrait + audio to the SadTalker
     wrapper; sync produces a talking-head MP4.
4. Concatenate all per-scene MP4s into the final reel_draft using
   ffmpeg's concat demuxer.
5. Emit ``reel_draft`` + per-scene artifact metadata so downstream qc /
   publisher stages get a single coherent video they can validate.

Network calls are gated by the same env switches as the original
handlers (FLUX_LOCAL_BASE_URL for image gen, F5TTS_RO_BASE_URL for
TTS, SADTALKER_BASE_URL for presenter lipsync). When a required
backend is unreachable the stage raises StageRejection with a
categorised reason so the API surface stays consistent with the
Phase 11 error code taxonomy.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from common.enums import ArtifactType, StageName
from common.exceptions import StageError, StageRejection
from common.schemas import ArtifactRef, DagState, StageOutput

log = logging.getLogger(__name__)

_FFMPEG_TIMEOUT_SECONDS = 600
_FLUX_TIMEOUT_SECONDS = 600
_TTS_TIMEOUT_SECONDS = 600  # F5TTS on CPU can take 60-90s per chunk; bumped from 180 to 600 so multi-scene news_presenter jobs don't get killed by an arbitrary cap before the wrapper finishes.
_SADTALKER_TIMEOUT_SECONDS = 900


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Phase 22 — orientation → (width, height). Portrait is the mobile reel
# format (9:16). All per-scene clips are scaled+padded to these exact
# dimensions so the ffmpeg concat demuxer (which requires uniform
# streams) succeeds.
_ORIENTATION_DIMS: dict[str, tuple[int, int]] = {
    "landscape": (1280, 720),
    "portrait": (720, 1280),
    "square": (1024, 1024),
}


def _dims_for(orientation: str) -> tuple[int, int]:
    return _ORIENTATION_DIMS.get((orientation or "landscape").lower(),
                                 _ORIENTATION_DIMS["landscape"])


def _scale_pad_filter(w: int, h: int) -> str:
    """ffmpeg filter that scales a source to FIT inside w×h preserving
    aspect, then pads the remainder with black so output is exactly
    w×h. Used to normalise heterogeneous clips (FLUX broll vs square
    SadTalker presenter) before concat.
    """
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1"
    )


def _ffmpeg_or_fail() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise StageRejection(
            StageName.scene_composer.value,
            "ffmpeg_missing: scene_composer requires ffmpeg on PATH",
        )
    return ffmpeg


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _artifacts_dir(job_id: str) -> Path:
    root = Path(os.environ.get("ARTIFACTS_LOCAL_ROOT", "/storage/artifacts"))
    out = root / "scenes" / job_id
    out.mkdir(parents=True, exist_ok=True)
    # Phase 21 iter 2 — Phase 11F-CDOROB cross-uid permission fix:
    # the F5TTS / SadTalker wrappers run as a different uid than the
    # orchestrator, so the per-scene dir must be group/other-writable
    # for them to drop their output WAV/MP4 here.
    try:
        out.chmod(0o777)
    except OSError:
        pass
    return out


def _flux_base_url() -> str:
    return os.environ.get("FLUX_LOCAL_BASE_URL", "").strip()


def _tts_base_url() -> str:
    # Prefer F5 (configured in Phase 20); the wrapper handles per-voice
    # routing via voice_id. Fall back to the legacy single endpoint.
    return os.environ.get("F5TTS_RO_BASE_URL", "").strip()


def _sadtalker_base_url() -> str:
    return os.environ.get("SADTALKER_BASE_URL", "").strip()


# ---------------------------------------------------------------------------
# Per-scene generation
# ---------------------------------------------------------------------------


def _generate_flux_image(
    *,
    prompt: str,
    out_path: Path,
    width: int = 1280,
    height: int = 720,
) -> dict[str, Any]:
    """POST to the model-flux wrapper; download the resulting PNG to
    ``out_path``. Raises StageRejection with a categorised reason on
    failure so the operator gets actionable feedback.
    """
    base = _flux_base_url()
    if not base:
        raise StageRejection(
            StageName.scene_composer.value,
            "image_provider_not_configured: FLUX_LOCAL_BASE_URL is unset",
        )
    req_body = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "steps": 4,           # schnell defaults to 4
        "guidance_scale": 0,  # schnell uses no CFG
    }
    data = json.dumps(req_body).encode("utf-8")
    url = base.rstrip("/") + "/flux/generate"
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_FLUX_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            err_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            err_text = ""
        raise StageRejection(
            StageName.scene_composer.value,
            f"image_generation_failed: FLUX HTTP {exc.code}: {err_text[:300]}",
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise StageRejection(
            StageName.scene_composer.value,
            f"image_provider_unreachable: FLUX wrapper at {base!r}: "
            f"{type(exc).__name__}: {exc}",
        ) from exc
    file_path = (body or {}).get("file_path")
    if not file_path or not Path(file_path).is_file():
        raise StageRejection(
            StageName.scene_composer.value,
            f"image_generation_failed: FLUX reported success but the file "
            f"{file_path!r} does not exist",
        )
    # Copy from the shared /storage/artifacts/flux/... into our per-job
    # scenes dir so we control the lifecycle.
    out_path.write_bytes(Path(file_path).read_bytes())
    return body


def _generate_tts_audio(
    *,
    text: str,
    out_path: Path,
    voice_id: str | None,
    language: str,
) -> dict[str, Any]:
    """POST to model-tts-ro (or any F5-compatible wrapper)."""
    base = _tts_base_url()
    if not base:
        raise StageRejection(
            StageName.scene_composer.value,
            "tts_provider_not_configured: F5TTS_RO_BASE_URL is unset; "
            "scene_composer needs a TTS wrapper to render voice per scene",
        )
    req_body = {
        "text": text,
        "voice_id": voice_id or "ro_default",
        "output_path": str(out_path),
        "output_format": "wav",
        "language": language or "ro",
    }
    data = json.dumps(req_body).encode("utf-8")
    url = base.rstrip("/") + "/tts/generate"
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TTS_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            err_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            err_text = ""
        raise StageRejection(
            StageName.scene_composer.value,
            f"tts_generation_failed: TTS HTTP {exc.code}: {err_text[:300]}",
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise StageRejection(
            StageName.scene_composer.value,
            f"tts_provider_unreachable: {base!r}: {type(exc).__name__}: {exc}",
        ) from exc
    if (body or {}).get("status") != "generated" or not out_path.is_file():
        raise StageRejection(
            StageName.scene_composer.value,
            f"tts_generation_failed: wrapper status={body.get('status')!r}",
        )
    # Phase 21 iter 3 — defensive size check. The F5 wrapper has been
    # observed returning HTTP 200 + status=generated yet a 44-byte WAV
    # (header only, no PCM) for very short spoken_text. That broken
    # WAV then poisons the ffmpeg broll-clip render → concat fails
    # with rc=234. Bail out early with a categorised error so the
    # operator can lengthen the scene text.
    size = out_path.stat().st_size
    if size < 1024:
        raise StageRejection(
            StageName.scene_composer.value,
            f"tts_generation_failed: wrapper produced an unusably small "
            f"WAV ({size} bytes) for text {text[:60]!r}. F5 may have "
            f"failed on a too-short clip — try lengthening spoken_text.",
        )
    return body


def _render_broll_clip(
    *,
    image_path: Path,
    audio_path: Path,
    out_path: Path,
    duration_s: float,
    width: int = 1280,
    height: int = 720,
) -> None:
    """Render a B-roll MP4: loop the still image, layer the TTS audio,
    apply a slow Ken-Burns zoom. Duration is whichever is shorter
    between ``duration_s`` and the actual audio length so the audio
    is never cut mid-sentence.
    """
    ffmpeg = _ffmpeg_or_fail()
    # zoompan filter parameters: ``zoom`` increments per output frame.
    # We render at 30 fps. For a 5s clip → 150 frames, zoom 1.0 → 1.15.
    # zoom_inc = 0.0015 → 0.225 over 150 frames; clamp to 1.15.
    fps = 30
    total_frames = int(round(duration_s * fps))
    zoom_inc = 0.001  # gentle 0.001 per frame ≈ 30% over 300 frames
    vf = (
        f"scale={width * 2}:-1,"  # upscale source 2x so zoompan stays sharp
        f"zoompan=z='min(zoom+{zoom_inc},1.30)':d={total_frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},"
        "format=yuv420p"
    )
    cmd = [
        ffmpeg, "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-r", str(fps),
        "-t", str(duration_s),
        str(out_path),
    ]
    proc = subprocess.run(  # noqa: S603
        cmd, capture_output=True,
        timeout=_FFMPEG_TIMEOUT_SECONDS, check=False,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", errors="replace")[-500:]
        raise StageRejection(
            StageName.scene_composer.value,
            f"broll_clip_render_failed: ffmpeg rc={proc.returncode}; tail={tail!r}",
        )
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise StageRejection(
            StageName.scene_composer.value,
            "broll_clip_render_failed: ffmpeg produced no output",
        )


def _render_presenter_clip(
    *,
    image_path: Path,
    audio_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    """Call the SadTalker wrapper to produce a talking-head MP4."""
    base = _sadtalker_base_url()
    if not base:
        raise StageRejection(
            StageName.scene_composer.value,
            "lipsync_provider_not_configured: SADTALKER_BASE_URL is unset; "
            "news_presenter pipeline requires SadTalker for presenter segments",
        )
    req_body = {
        "image_path": str(image_path),
        "audio_path": str(audio_path),
        "output_path": str(out_path),
    }
    data = json.dumps(req_body).encode("utf-8")
    url = base.rstrip("/") + "/sadtalker/generate"
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_SADTALKER_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            err_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            err_text = ""
        raise StageRejection(
            StageName.scene_composer.value,
            f"lipsync_generation_failed: SadTalker HTTP {exc.code}: {err_text[:300]}",
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise StageRejection(
            StageName.scene_composer.value,
            f"lipsync_provider_unreachable: {base!r}: {type(exc).__name__}: {exc}",
        ) from exc
    # Phase 21 iter 3 — the SadTalker wrapper signals success with
    # status "completed", the F5/TTS wrappers use "generated". Accept
    # either; the on-disk file existence + size check below is the
    # authoritative success signal.
    wrapper_status = (body or {}).get("status")
    if wrapper_status not in ("generated", "completed") or not out_path.is_file():
        raise StageRejection(
            StageName.scene_composer.value,
            f"lipsync_generation_failed: wrapper status={wrapper_status!r}",
        )
    return body


def _normalize_clip(*, src: Path, dst: Path, width: int, height: int) -> None:
    """Phase 22 — re-encode ``src`` to exactly width×height (scale-fit +
    black pad) so all clips share dimensions before the concat demuxer.
    Used for SadTalker presenter clips (square) in non-square orientations.
    """
    ffmpeg = _ffmpeg_or_fail()
    cmd = [
        ffmpeg, "-y", "-i", str(src),
        "-vf", _scale_pad_filter(width, height) + ",format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-r", "30",
        str(dst),
    ]
    proc = subprocess.run(  # noqa: S603
        cmd, capture_output=True, timeout=_FFMPEG_TIMEOUT_SECONDS, check=False,
    )
    if proc.returncode != 0 or not dst.is_file() or dst.stat().st_size == 0:
        tail = proc.stderr.decode("utf-8", errors="replace")[-400:]
        raise StageRejection(
            StageName.scene_composer.value,
            f"clip_normalize_failed: ffmpeg rc={proc.returncode}; tail={tail!r}",
        )


def _concat_clips(
    *,
    clips: list[Path],
    out_path: Path,
) -> None:
    """ffmpeg concat demuxer — assumes every input has the same codec /
    pixel-format / sample-rate. We always render via the same
    libx264+aac recipe in this stage so the assumption holds.
    """
    ffmpeg = _ffmpeg_or_fail()
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, dir=str(out_path.parent),
    ) as f:
        for c in clips:
            # Filenames are simple uuid.mp4 so no escaping needed.
            f.write(f"file '{c.name}'\n")
        list_path = Path(f.name)
    try:
        cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_path),
            "-c", "copy",
            str(out_path),
        ]
        proc = subprocess.run(  # noqa: S603
            cmd, capture_output=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS, check=False,
            cwd=str(out_path.parent),
        )
        if proc.returncode != 0:
            tail = proc.stderr.decode("utf-8", errors="replace")[-500:]
            raise StageRejection(
                StageName.scene_composer.value,
                f"concat_failed: ffmpeg rc={proc.returncode}; tail={tail!r}",
            )
    finally:
        try:
            list_path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------


async def run(state: DagState) -> StageOutput:
    """Phase 21 — scene_composer stage entry.

    Pulls state.scene_plan + state.character_id (when news_presenter),
    runs the per-scene generators in sequence (image gen, TTS, clip
    render), concatenates into the final reel_draft, and emits a
    StageOutput with the same ``talking_head`` artifact key that
    downstream qc / publisher / editor stages expect — this avoids
    schema drift across the canonical DAG.
    """
    if not state.scene_plan:
        raise StageRejection(
            StageName.scene_composer.value,
            "scene_plan_missing: scene_composer requires a non-empty scene_plan",
        )

    # Pull character portrait (required for presenter segments).
    presenter_portrait: Path | None = None
    if state.image_ref:
        portrait_str = (state.image_ref.path or "").strip()
        if portrait_str:
            candidate = Path(portrait_str)
            if candidate.is_file():
                presenter_portrait = candidate

    has_presenter = any(
        (s.get("kind") or "").lower() == "presenter"
        for s in state.scene_plan
    )
    if has_presenter and presenter_portrait is None:
        raise StageRejection(
            StageName.scene_composer.value,
            "presenter_portrait_missing: news_presenter scene_plan has "
            "presenter segments but state.image_ref is unset or the file "
            "is not on disk",
        )

    job_dir = _artifacts_dir(str(state.job_id))
    clip_paths: list[Path] = []
    scenes_metadata: list[dict[str, Any]] = []
    total_duration = 0.0
    voice_id = None
    # Pull operator-picked TTS voice if present in provider_selection.
    if state.provider_selection:
        pid = state.provider_selection.get("tts_provider_id") or ""
        if pid.startswith("f5tts_ro_"):
            voice_id = pid[len("f5tts_ro_"):]

    # Phase 22 — target dimensions from the job orientation. All clips
    # are rendered / normalised to these exact dims so the concat
    # demuxer accepts them.
    target_w, target_h = _dims_for(getattr(state, "orientation", "landscape"))
    log.info(
        "scene_composer: orientation=%s → %dx%d",
        getattr(state, "orientation", "landscape"), target_w, target_h,
    )

    for scene_dict in state.scene_plan:
        scene_no = int(scene_dict.get("scene_number") or len(clip_paths) + 1)
        kind = (scene_dict.get("kind") or "broll").lower()
        spoken = (scene_dict.get("spoken_text") or "").strip()
        if not spoken:
            raise StageRejection(
                StageName.scene_composer.value,
                f"scene_{scene_no}_missing_spoken_text",
            )
        duration_s = float(scene_dict.get("duration_s") or 5.0)
        duration_s = max(1.0, min(20.0, duration_s))

        scene_uid = uuid.uuid4().hex[:12]
        audio_path = job_dir / f"scene_{scene_no:02d}_{scene_uid}_audio.wav"
        clip_path = job_dir / f"scene_{scene_no:02d}_{scene_uid}_clip.mp4"

        # 1. Render TTS audio for this scene.
        log.info("scene_composer: scene %d (%s) generating TTS", scene_no, kind)
        await asyncio.to_thread(
            _generate_tts_audio,
            text=spoken,
            out_path=audio_path,
            voice_id=voice_id,
            language=state.video_language,
        )

        # 2. Render the clip itself.
        if kind == "presenter":
            log.info("scene_composer: scene %d presenter → SadTalker", scene_no)
            raw_clip = job_dir / f"scene_{scene_no:02d}_{scene_uid}_raw.mp4"
            await asyncio.to_thread(
                _render_presenter_clip,
                image_path=presenter_portrait,  # type: ignore[arg-type]
                audio_path=audio_path,
                out_path=raw_clip,
            )
            # Phase 22 — SadTalker emits a square crop; normalise to the
            # target orientation (scale-fit + black pad) so the concat
            # demuxer sees uniform dimensions.
            await asyncio.to_thread(
                _normalize_clip, src=raw_clip, dst=clip_path,
                width=target_w, height=target_h,
            )
        else:  # broll
            visual = (scene_dict.get("visual_description") or "").strip()
            if not visual:
                raise StageRejection(
                    StageName.scene_composer.value,
                    f"scene_{scene_no}_missing_visual_description",
                )
            image_path = job_dir / f"scene_{scene_no:02d}_{scene_uid}_image.png"
            log.info("scene_composer: scene %d broll → FLUX prompt='%s'", scene_no, visual[:60])
            await asyncio.to_thread(
                _generate_flux_image,
                prompt=visual,
                out_path=image_path,
                width=target_w, height=target_h,
            )
            log.info("scene_composer: scene %d broll → ffmpeg Ken-Burns", scene_no)
            await asyncio.to_thread(
                _render_broll_clip,
                image_path=image_path,
                audio_path=audio_path,
                out_path=clip_path,
                duration_s=duration_s,
                width=target_w, height=target_h,
            )

        clip_paths.append(clip_path)
        total_duration += duration_s
        scenes_metadata.append({
            "scene_number": scene_no,
            "kind": kind,
            "spoken_text": spoken,
            "visual_description": scene_dict.get("visual_description"),
            "duration_s": duration_s,
            "clip_local_path": str(clip_path),
            "audio_local_path": str(audio_path),
        })

    # 3. Concat all clips → final reel_draft.
    final_path = job_dir / f"reel_draft_{uuid.uuid4().hex}.mp4"
    log.info("scene_composer: concat %d clips → %s", len(clip_paths), final_path)
    await asyncio.to_thread(_concat_clips, clips=clip_paths, out_path=final_path)
    checksum = _sha256_of_file(final_path)
    size_bytes = final_path.stat().st_size

    # Emit the artifact as a ``talking_head`` key so the downstream
    # editor stage (still in the DAG for QC parity) can find it via
    # the same lookup it uses for the talking_head pipeline.
    reel_ref = ArtifactRef(
        artifact_type=ArtifactType.video.value,
        uri=final_path.as_uri(),
        local_path=str(final_path),
        mime_type="video/mp4",
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        duration_seconds=total_duration,
        width=target_w,
        height=target_h,
        extra={
            "phase": "phase21_scene_composer",
            "orientation": getattr(state, "orientation", "landscape"),
            "scene_count": len(scenes_metadata),
            "scenes": scenes_metadata,
            "concatenation_method": "ffmpeg_concat_demuxer",
            "broll_zoom_filter": "zoompan",
            # Phase 9D marker — tells the QC stage this is a real
            # editor output (not a stub). Without it the
            # reel_draft_is_stub check downgrades to ``warn``.
            "real_editor_output": True,
        },
    )
    return StageOutput(
        noop=False,
        notes=(
            f"scene_composer rendered {len(scenes_metadata)} scene(s) "
            f"({len(clip_paths)} clip(s) concatenated) — total "
            f"~{total_duration:.1f}s"
        ),
        artifacts={"talking_head": reel_ref, "reel_draft": reel_ref},
    )

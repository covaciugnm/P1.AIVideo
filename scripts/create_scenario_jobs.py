"""Phase 8E + Phase 10A-0 scenario / demo job seeder.

Creates one job per realistic path through P1.AIVideo so an operator
can inspect every provider-selection combination in the UI without
actually running real GPU inference or paid APIs.

Two modes:

- ``run(...)`` (default) — Phase 8E scenarios, timestamped, append-only.
- ``run_demo(...)`` — Phase 10A-0 "Demo —" matrix (8 stable scenarios).
  Idempotent: queries ``/api/v1/jobs`` first and skips any
  ``Demo — <label>`` that already exists. Scenario 8 (Real video
  success) only attempts creation when SadTalker readiness is green.

Safety contract:

- Never deletes existing jobs / artifacts / volumes.
- Never calls a real GPU / paid API. If a provider isn't configured
  (Piper, SadTalker, Ollama, etc.) the scenario *expects* the
  ``not_configured`` / ``runtime_missing`` path — and the operator can
  inspect that clean failure in the UI.
- No binary fixtures shipped in repo. Tiny WAV / PNG fixtures are
  generated in-memory by stdlib (``wave`` + a PNG encoder) and
  uploaded via the existing ``/api/v1/uploads/{audio,image}`` API.
- A real MP3 sample is generated via ``ffmpeg`` if available on the
  backend; otherwise the MP3 scenario reports "skipped, no ffmpeg".

Usage:

    BACKEND_BASE_URL=http://localhost:8001 \
      python scripts/create_scenario_jobs.py            # Phase 8E
    BACKEND_BASE_URL=http://localhost:8001 \
      python scripts/create_scenario_jobs.py --demo     # Phase 10A-0

Outputs: a JSON summary of created job IDs printed to stdout + brief
human-readable status lines.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
import zlib
from datetime import datetime, timezone


DEFAULT_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://localhost:8001")


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def _post_json(base: str, path: str, body: dict) -> tuple[int, dict | str]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(text)
            except json.JSONDecodeError:
                return resp.status, text
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body_text)
        except json.JSONDecodeError:
            return exc.code, body_text


def _post_multipart(
    base: str, path: str, *, field: str, filename: str, content: bytes, mime: str
) -> tuple[int, dict | str]:
    boundary = f"----aivideo-scenario-{int(time.time() * 1000)}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    body += content
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(text)
            except json.JSONDecodeError:
                return resp.status, text
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body_text)
        except json.JSONDecodeError:
            return exc.code, body_text


def _get_json(base: str, path: str) -> tuple[int, dict | list | str]:
    req = urllib.request.Request(
        f"{base}{path}", method="GET", headers={"Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(text)
            except json.JSONDecodeError:
                return resp.status, text
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def _make_tiny_wav() -> bytes:
    """22.05 kHz mono PCM WAV, 300 ms of silence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 6615)
    return buf.getvalue()


def _make_tiny_png(w: int = 64, h: int = 64) -> bytes:
    """64×64 solid-white PNG via stdlib."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"IHDR" + struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr_chunk = (
        struct.pack(">I", 13) + ihdr + struct.pack(">I", zlib.crc32(ihdr) & 0xFFFFFFFF)
    )
    raw = b"".join(b"\x00" + b"\xFF\xFF\xFF" * w for _ in range(h))
    idat = b"IDAT" + zlib.compress(raw)
    idat_chunk = (
        struct.pack(">I", len(idat) - 4)
        + idat
        + struct.pack(">I", zlib.crc32(idat) & 0xFFFFFFFF)
    )
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(
        ">I", zlib.crc32(b"IEND") & 0xFFFFFFFF
    )
    return sig + ihdr_chunk + idat_chunk + iend_chunk


def _make_tiny_mp3_via_ffmpeg() -> bytes | None:
    """Use ffmpeg (if available on the *host*) to generate a 0.3 s
    silent MP3. Returns None if ffmpeg isn't on PATH."""
    import shutil
    import subprocess
    import tempfile

    if shutil.which("ffmpeg") is None:
        return None
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
        out_path = tf.name
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=cl=mono:r=22050:d=0.3",
                "-codec:a",
                "libmp3lame",
                "-qscale:a",
                "9",
                out_path,
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )
        with open(out_path, "rb") as f:
            return f.read()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def _base_brief(n: int, label: str, stamp: str) -> str:
    return f"Scenario {n} — {label} [seeded {stamp}]"


def _base_payload(brief: str, **overrides) -> dict:
    body = {
        "brief": brief,
        "target_duration_seconds": 30,
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "watermark_required": True,
        "c2pa_required": True,
        "voice_mode": "tts",
        "script_text": (
            "Three calming bedtime habits for better sleep: dim the "
            "lights, stretch slowly, and write tomorrow's first task."
        ),
    }
    body.update(overrides)
    return body


def _create_job(
    base: str, payload: dict
) -> tuple[bool, str | None, dict | str, int]:
    code, body = _post_json(base, "/api/v1/jobs/from-inputs", payload)
    if code == 201 and isinstance(body, dict):
        return True, body.get("id"), body, code
    return False, None, body, code


def _upload(
    base: str, kind: str, content: bytes, filename: str, mime: str
) -> tuple[bool, str | None, dict | str, int]:
    code, body = _post_multipart(
        base,
        f"/api/v1/uploads/{kind}",
        field="file",
        filename=filename,
        content=content,
        mime=mime,
    )
    if code == 201 and isinstance(body, dict):
        return True, body.get("artifact_id"), body, code
    return False, None, body, code


def run(base_url: str) -> dict:
    stamp = _now_stamp()
    results: list[dict] = []

    def record(scenario: int, label: str, ok: bool, **extra) -> None:
        entry = {
            "scenario": scenario,
            "label": label,
            "status": "ok" if ok else "failed",
            **extra,
        }
        results.append(entry)
        flag = "PASS" if ok else "FAIL"
        print(
            f"[{flag}] Scenario {scenario}: {label}"
            + ("" if "job_id" not in extra else f" → job_id={extra['job_id']}"),
            file=sys.stderr,
        )

    # ---- Sanity-check backend ----
    code, _ = _get_json(base_url, "/healthz")
    if code != 200:
        print(
            json.dumps(
                {
                    "stamp": stamp,
                    "base_url": base_url,
                    "error": f"backend /healthz returned {code}",
                    "scenarios": [],
                }
            )
        )
        sys.exit(1)

    # ---- Scenario 1: template + TTS path ----
    ok, jid, body, code = _create_job(
        base_url,
        _base_payload(
            _base_brief(1, "template script + TTS (Piper)", stamp),
            voice_mode="tts",
            provider_selection={
                "script_provider_id": "template",
                "tts_provider_id": "piper",
            },
        ),
    )
    record(1, "Template + Piper TTS", ok, job_id=jid, http=code)

    # ---- Scenario 2: mock + TTS path ----
    ok, jid, body, code = _create_job(
        base_url,
        _base_payload(
            _base_brief(2, "mock script + TTS (Piper)", stamp),
            voice_mode="tts",
            provider_selection={
                "script_provider_id": "mock",
                "tts_provider_id": "piper",
            },
        ),
    )
    record(2, "Mock + Piper TTS", ok, job_id=jid, http=code)

    # ---- Scenario 3: provided WAV upload + audio_processor ----
    ok, aid, _body, code = _upload(
        base_url,
        "audio",
        _make_tiny_wav(),
        "scenario3.wav",
        "audio/wav",
    )
    if not ok:
        record(3, "Provided WAV upload", False, http=code, detail=_body)
    else:
        ok2, jid, body, code2 = _create_job(
            base_url,
            _base_payload(
                _base_brief(3, "provided WAV + ffmpeg_convert", stamp),
                voice_mode="provided_audio",
                audio_artifact_id=aid,
                audio_consent_confirmed=True,
                audio_synthetic_or_owned=True,
                script_text=None,
                provider_selection={
                    "audio_processor_id": "ffmpeg_convert",
                },
            ),
        )
        record(
            3,
            "Provided WAV + ffmpeg_convert",
            ok2,
            job_id=jid,
            audio_artifact_id=aid,
            http=code2,
        )

    # ---- Scenario 4: provided MP3 (ffmpeg-gated) ----
    mp3 = _make_tiny_mp3_via_ffmpeg()
    if mp3 is None:
        record(4, "Provided MP3 → WAV", False, skipped="no ffmpeg on host")
    else:
        ok, aid, _body, code = _upload(
            base_url, "audio", mp3, "scenario4.mp3", "audio/mpeg"
        )
        if not ok:
            record(4, "Provided MP3 upload", False, http=code, detail=_body)
        else:
            converted = (
                isinstance(_body, dict)
                and (_body.get("metadata_summary") or {}).get(
                    "converted_to_wav"
                )
            )
            ok2, jid, body, code2 = _create_job(
                base_url,
                _base_payload(
                    _base_brief(4, "provided MP3 transcoded to WAV", stamp),
                    voice_mode="provided_audio",
                    audio_artifact_id=aid,
                    audio_consent_confirmed=True,
                    audio_synthetic_or_owned=True,
                    script_text=None,
                ),
            )
            record(
                4,
                "Provided MP3 → WAV",
                ok2,
                job_id=jid,
                audio_artifact_id=aid,
                converted_to_wav=bool(converted),
                http=code2,
            )

    # ---- Scenario 5: image validation path ----
    ok, iid, _body, code = _upload(
        base_url, "image", _make_tiny_png(), "scenario5.png", "image/png"
    )
    if not ok:
        record(5, "Image upload", False, http=code, detail=_body)
    else:
        ok2, jid, body, code2 = _create_job(
            base_url,
            _base_payload(
                _base_brief(5, "image upload + stdlib_image_validation", stamp),
                face_mode="provided_image",
                image_artifact_id=iid,
                image_consent_confirmed=True,
                image_synthetic_person_confirmed=True,
                provider_selection={
                    "image_processor_id": "stdlib_image_validation",
                },
            ),
        )
        record(
            5,
            "Image + stdlib_image_validation",
            ok2,
            job_id=jid,
            image_artifact_id=iid,
            http=code2,
        )

    # ---- Scenario 6: provided audio + image + SadTalker ----
    ok_a, aid, _body_a, _c_a = _upload(
        base_url, "audio", _make_tiny_wav(), "scenario6.wav", "audio/wav"
    )
    ok_i, iid, _body_i, _c_i = _upload(
        base_url, "image", _make_tiny_png(), "scenario6.png", "image/png"
    )
    if not (ok_a and ok_i):
        record(6, "Audio+image+SadTalker upload", False)
    else:
        ok2, jid, body, code2 = _create_job(
            base_url,
            _base_payload(
                _base_brief(6, "provided audio + image + SadTalker", stamp),
                voice_mode="provided_audio",
                face_mode="provided_image",
                audio_artifact_id=aid,
                audio_consent_confirmed=True,
                audio_synthetic_or_owned=True,
                image_artifact_id=iid,
                image_consent_confirmed=True,
                image_synthetic_person_confirmed=True,
                script_text=None,
                provider_selection={
                    "video_provider_id": "sadtalker",
                    "audio_processor_id": "ffmpeg_convert",
                    "image_processor_id": "stdlib_image_validation",
                },
            ),
        )
        record(
            6,
            "Audio+image+SadTalker (expect not_configured at runtime)",
            ok2,
            job_id=jid,
            audio_artifact_id=aid,
            image_artifact_id=iid,
            http=code2,
        )

    # ---- Scenario 7: full provider matrix ----
    ok, jid, body, code = _create_job(
        base_url,
        _base_payload(
            _base_brief(7, "full provider matrix", stamp),
            provider_selection={
                "script_provider_id": "template",
                "tts_provider_id": "piper",
                "video_provider_id": "sadtalker",
                "audio_processor_id": "ffmpeg_convert",
                "image_processor_id": "stdlib_image_validation",
            },
        ),
    )
    record(7, "Full provider matrix", ok, job_id=jid, http=code)

    # ---- Scenario 8: unknown / future provider ids ----
    ok, jid, body, code = _create_job(
        base_url,
        _base_payload(
            _base_brief(8, "future / unknown provider ids", stamp),
            provider_selection={
                "script_provider_id": "custom_future_llm",
                "tts_provider_id": "custom_future_tts",
                "video_provider_id": "custom_future_video",
            },
        ),
    )
    record(8, "Future unknown provider ids", ok, job_id=jid, http=code)

    # ---- Tally ----
    total = len(results)
    okc = sum(1 for r in results if r["status"] == "ok")
    summary = {
        "stamp": stamp,
        "base_url": base_url,
        "passed": okc,
        "total": total,
        "scenarios": results,
    }
    return summary


# ---------------------------------------------------------------------------
# Phase 10A-0 — "Demo —" matrix (idempotent)
# ---------------------------------------------------------------------------


_DEMO_BRIEFS = (
    "Demo — Template Script + TTS Piper path",
    "Demo — Mock Script + TTS Piper path",
    "Demo — Ollama Script path",
    "Demo — Provided WAV audio + Provided image + SadTalker selected",
    "Demo — MP3 upload conversion path",
    "Demo — Future custom providers metadata path",
    "Demo — Full local best-effort path",
    "Demo — Real video success",
)


def _existing_demo_jobs(base: str) -> dict[str, str]:
    """Return ``{brief: job_id}`` for every existing job whose brief
    starts with ``"Demo —"``. Used to make ``run_demo()`` idempotent."""
    code, body = _get_json(base, "/api/v1/jobs")
    if code != 200 or not isinstance(body, list):
        return {}
    out: dict[str, str] = {}
    for j in body:
        brief = (j.get("brief") or "").strip()
        if brief.startswith("Demo —") and j.get("id"):
            out.setdefault(brief, j["id"])
    return out


def _sadtalker_ready(base: str) -> tuple[bool, dict]:
    """Cheap readiness probe via the providers catalog. Returns
    ``(True, details)`` only when the SadTalker status is exactly
    ``available`` *and* the operator has set the real-inference env
    flags. Used to decide whether to attempt Scenario 8."""
    code, body = _get_json(base, "/api/v1/providers")
    if code != 200 or not isinstance(body, dict):
        return False, {"error": "providers catalog unreachable"}
    sad = None
    for p in body.get("video_generator", []) or []:
        if p.get("provider_id") == "sadtalker":
            sad = p
            break
    if sad is None:
        return False, {"error": "sadtalker not in catalog"}
    status = sad.get("status")
    real_flag = os.environ.get("SADTALKER_ENABLE_REAL_INFERENCE", "").lower() == "true"
    run_flag = os.environ.get("RUN_REAL_SADTALKER", "") == "1"
    ready = status == "available" and real_flag and run_flag
    return ready, {
        "status": status,
        "SADTALKER_ENABLE_REAL_INFERENCE": real_flag,
        "RUN_REAL_SADTALKER": run_flag,
    }


def run_demo(base_url: str) -> dict:
    """Phase 10A-0 — create the 8-scenario "Demo —" matrix idempotently.

    Each scenario records: existed_already, created_now, job_id,
    artifact_ids, http codes, and (for scenario 8) the missing
    SadTalker gates that prevented creation."""
    existing = _existing_demo_jobs(base_url)
    results: list[dict] = []

    def _ensure_job(scenario: int, brief: str, payload: dict) -> dict:
        if brief in existing:
            return {
                "scenario": scenario,
                "brief": brief,
                "existed_already": True,
                "created_now": False,
                "job_id": existing[brief],
                "ui_url": f"http://localhost:3010/jobs/{existing[brief]}",
            }
        payload = dict(payload)
        payload["brief"] = brief
        ok, jid, body, code = _create_job(base_url, payload)
        entry = {
            "scenario": scenario,
            "brief": brief,
            "existed_already": False,
            "created_now": bool(ok),
            "http": code,
            "job_id": jid,
        }
        if not ok:
            entry["error_body"] = body
        else:
            entry["ui_url"] = f"http://localhost:3010/jobs/{jid}"
        return entry

    base_kwargs = {
        "target_duration_seconds": 30,
        "synthetic_person_confirmed": True,
        "consent_confirmed": True,
        "watermark_required": True,
        "c2pa_required": True,
    }
    demo_script = (
        "Three calming bedtime habits for better sleep: dim the "
        "lights, stretch slowly, and write tomorrow's first task."
    )

    # ----- Scenario 1 — Template Script + TTS Piper path -----
    results.append(
        _ensure_job(
            1,
            _DEMO_BRIEFS[0],
            {
                **base_kwargs,
                "voice_mode": "tts",
                "script_text": demo_script,
                "provider_selection": {
                    "script_provider_id": "template",
                    "tts_provider_id": "piper",
                    "video_provider_id": "sadtalker",
                    "audio_processor_id": "ffmpeg_convert",
                    "image_processor_id": "stdlib_image_validation",
                },
            },
        )
    )

    # ----- Scenario 2 — Mock Script + TTS Piper path -----
    results.append(
        _ensure_job(
            2,
            _DEMO_BRIEFS[1],
            {
                **base_kwargs,
                "voice_mode": "tts",
                "script_text": demo_script,
                "provider_selection": {
                    "script_provider_id": "mock",
                    "tts_provider_id": "piper",
                    "video_provider_id": "sadtalker",
                    "audio_processor_id": "ffmpeg_convert",
                    "image_processor_id": "stdlib_image_validation",
                },
            },
        )
    )

    # ----- Scenario 3 — Ollama Script path -----
    results.append(
        _ensure_job(
            3,
            _DEMO_BRIEFS[2],
            {
                **base_kwargs,
                "voice_mode": "tts",
                "script_text": demo_script,
                "provider_selection": {
                    "script_provider_id": "ollama",
                    "script_model": os.environ.get(
                        "DEMO_OLLAMA_MODEL", "qwen3.6"
                    ),
                    "tts_provider_id": "piper",
                    "video_provider_id": "sadtalker",
                    "audio_processor_id": "ffmpeg_convert",
                    "image_processor_id": "stdlib_image_validation",
                },
            },
        )
    )

    # ----- Scenario 4 — Provided WAV + Provided image + SadTalker -----
    if _DEMO_BRIEFS[3] in existing:
        results.append(
            {
                "scenario": 4,
                "brief": _DEMO_BRIEFS[3],
                "existed_already": True,
                "created_now": False,
                "job_id": existing[_DEMO_BRIEFS[3]],
                "ui_url": f"http://localhost:3010/jobs/{existing[_DEMO_BRIEFS[3]]}",
            }
        )
    else:
        ok_a, aid, _body_a, code_a = _upload(
            base_url, "audio", _make_tiny_wav(), "demo4.wav", "audio/wav"
        )
        ok_i, iid, _body_i, code_i = _upload(
            base_url, "image", _make_tiny_png(), "demo4.png", "image/png"
        )
        if not (ok_a and ok_i):
            results.append(
                {
                    "scenario": 4,
                    "brief": _DEMO_BRIEFS[3],
                    "existed_already": False,
                    "created_now": False,
                    "error": "audio or image upload failed",
                    "http_audio": code_a,
                    "http_image": code_i,
                }
            )
        else:
            payload = {
                **base_kwargs,
                "brief": _DEMO_BRIEFS[3],
                "voice_mode": "provided_audio",
                "face_mode": "provided_image",
                "audio_artifact_id": aid,
                "audio_consent_confirmed": True,
                "audio_synthetic_or_owned": True,
                "image_artifact_id": iid,
                "image_consent_confirmed": True,
                "image_synthetic_person_confirmed": True,
                "script_text": None,
                "provider_selection": {
                    "script_provider_id": "template",
                    "tts_provider_id": "piper",
                    "video_provider_id": "sadtalker",
                    "audio_processor_id": "ffmpeg_convert",
                    "image_processor_id": "stdlib_image_validation",
                },
            }
            ok, jid, body, code = _create_job(base_url, payload)
            entry = {
                "scenario": 4,
                "brief": _DEMO_BRIEFS[3],
                "existed_already": False,
                "created_now": bool(ok),
                "http": code,
                "audio_artifact_id": aid,
                "image_artifact_id": iid,
                "job_id": jid,
            }
            if not ok:
                entry["error_body"] = body
            else:
                entry["ui_url"] = f"http://localhost:3010/jobs/{jid}"
            results.append(entry)

    # ----- Scenario 5 — MP3 upload conversion path -----
    if _DEMO_BRIEFS[4] in existing:
        results.append(
            {
                "scenario": 5,
                "brief": _DEMO_BRIEFS[4],
                "existed_already": True,
                "created_now": False,
                "job_id": existing[_DEMO_BRIEFS[4]],
                "ui_url": f"http://localhost:3010/jobs/{existing[_DEMO_BRIEFS[4]]}",
            }
        )
    else:
        mp3 = _make_tiny_mp3_via_ffmpeg()
        if mp3 is None:
            results.append(
                {
                    "scenario": 5,
                    "brief": _DEMO_BRIEFS[4],
                    "existed_already": False,
                    "created_now": False,
                    "skipped": "ffmpeg not available on host — MP3 fixture cannot be generated",
                }
            )
        else:
            ok, aid, body, code = _upload(
                base_url, "audio", mp3, "demo5.mp3", "audio/mpeg"
            )
            if not ok:
                results.append(
                    {
                        "scenario": 5,
                        "brief": _DEMO_BRIEFS[4],
                        "existed_already": False,
                        "created_now": False,
                        "error": "MP3 upload failed",
                        "http": code,
                        "error_body": body,
                    }
                )
            else:
                converted = (
                    isinstance(body, dict)
                    and (body.get("metadata_summary") or {}).get(
                        "converted_to_wav"
                    )
                )
                payload = {
                    **base_kwargs,
                    "brief": _DEMO_BRIEFS[4],
                    "voice_mode": "provided_audio",
                    "audio_artifact_id": aid,
                    "audio_consent_confirmed": True,
                    "audio_synthetic_or_owned": True,
                    "script_text": None,
                    "provider_selection": {
                        "script_provider_id": "template",
                        "tts_provider_id": "piper",
                        "video_provider_id": "sadtalker",
                        "audio_processor_id": "ffmpeg_convert",
                        "image_processor_id": "stdlib_image_validation",
                    },
                }
                ok2, jid, body2, code2 = _create_job(base_url, payload)
                entry = {
                    "scenario": 5,
                    "brief": _DEMO_BRIEFS[4],
                    "existed_already": False,
                    "created_now": bool(ok2),
                    "http": code2,
                    "audio_artifact_id": aid,
                    "converted_to_wav": bool(converted),
                    "job_id": jid,
                }
                if not ok2:
                    entry["error_body"] = body2
                else:
                    entry["ui_url"] = f"http://localhost:3010/jobs/{jid}"
                results.append(entry)

    # ----- Scenario 6 — Future custom providers metadata path -----
    results.append(
        _ensure_job(
            6,
            _DEMO_BRIEFS[5],
            {
                **base_kwargs,
                "voice_mode": "tts",
                "script_text": demo_script,
                "provider_selection": {
                    "script_provider_id": "custom_future_llm",
                    "tts_provider_id": "custom_future_tts",
                    "video_provider_id": "custom_future_video",
                    "audio_processor_id": "custom_future_audio_processor",
                    "image_processor_id": "custom_future_image_processor",
                },
            },
        )
    )

    # ----- Scenario 7 — Full local best-effort path -----
    results.append(
        _ensure_job(
            7,
            _DEMO_BRIEFS[6],
            {
                **base_kwargs,
                "voice_mode": "tts",
                "script_text": demo_script,
                "provider_selection": {
                    # The "best-effort" choice falls back to deterministic
                    # local providers when their real runtime isn't wired.
                    "script_provider_id": "template",
                    "tts_provider_id": "piper",
                    "video_provider_id": "sadtalker",
                    "audio_processor_id": "ffmpeg_convert",
                    "image_processor_id": "stdlib_image_validation",
                },
            },
        )
    )

    # ----- Scenario 8 — Real video success (only when SadTalker ready) -----
    sad_ready, sad_details = _sadtalker_ready(base_url)
    if _DEMO_BRIEFS[7] in existing:
        results.append(
            {
                "scenario": 8,
                "brief": _DEMO_BRIEFS[7],
                "existed_already": True,
                "created_now": False,
                "job_id": existing[_DEMO_BRIEFS[7]],
                "ui_url": f"http://localhost:3010/jobs/{existing[_DEMO_BRIEFS[7]]}",
            }
        )
    elif not sad_ready:
        results.append(
            {
                "scenario": 8,
                "brief": _DEMO_BRIEFS[7],
                "existed_already": False,
                "created_now": False,
                "skipped": (
                    "Skipped — SadTalker real runtime not ready "
                    "(no fake success will be claimed)"
                ),
                "missing_gates": sad_details,
            }
        )
    else:
        # SadTalker is ready. Upload tiny audio + image and create a job
        # that targets the real video provider.
        ok_a, aid, _body_a, _ = _upload(
            base_url, "audio", _make_tiny_wav(), "demo8.wav", "audio/wav"
        )
        ok_i, iid, _body_i, _ = _upload(
            base_url, "image", _make_tiny_png(), "demo8.png", "image/png"
        )
        if not (ok_a and ok_i):
            results.append(
                {
                    "scenario": 8,
                    "brief": _DEMO_BRIEFS[7],
                    "existed_already": False,
                    "created_now": False,
                    "error": "audio or image upload failed",
                }
            )
        else:
            payload = {
                **base_kwargs,
                "brief": _DEMO_BRIEFS[7],
                "voice_mode": "provided_audio",
                "face_mode": "provided_image",
                "audio_artifact_id": aid,
                "audio_consent_confirmed": True,
                "audio_synthetic_or_owned": True,
                "image_artifact_id": iid,
                "image_consent_confirmed": True,
                "image_synthetic_person_confirmed": True,
                "script_text": None,
                "provider_selection": {
                    "video_provider_id": "sadtalker",
                    "audio_processor_id": "ffmpeg_convert",
                    "image_processor_id": "stdlib_image_validation",
                },
            }
            ok, jid, body, code = _create_job(base_url, payload)
            entry = {
                "scenario": 8,
                "brief": _DEMO_BRIEFS[7],
                "existed_already": False,
                "created_now": bool(ok),
                "http": code,
                "audio_artifact_id": aid,
                "image_artifact_id": iid,
                "job_id": jid,
                "sadtalker_gates": sad_details,
            }
            if not ok:
                entry["error_body"] = body
            else:
                entry["ui_url"] = f"http://localhost:3010/jobs/{jid}"
            results.append(entry)

    created = sum(1 for r in results if r.get("created_now"))
    existed = sum(1 for r in results if r.get("existed_already"))
    skipped = sum(1 for r in results if r.get("skipped"))
    return {
        "base_url": base_url,
        "scenarios": results,
        "created_now": created,
        "existed_already": existed,
        "skipped": skipped,
        "total": len(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed P1.AIVideo scenario jobs.")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Backend base URL (default: {DEFAULT_BASE_URL!r})",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the Phase 10A-0 'Demo —' matrix (idempotent) instead of "
        "the legacy Phase 8E timestamped scenarios.",
    )
    args = parser.parse_args()
    if args.demo:
        summary = run_demo(args.base_url)
        print(json.dumps(summary, indent=2))
        # Treat skipped scenarios as informational, not failures —
        # Scenario 8 + MP3 path legitimately skip without GPU / ffmpeg.
        failed = sum(
            1 for r in summary["scenarios"]
            if not r.get("created_now")
            and not r.get("existed_already")
            and not r.get("skipped")
        )
        return 0 if failed == 0 else 2
    summary = run(args.base_url)
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] == summary["total"] else 2


if __name__ == "__main__":
    sys.exit(main())

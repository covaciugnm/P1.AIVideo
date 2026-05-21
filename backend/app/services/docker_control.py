"""On-demand Docker control via the mounted Engine socket.

The backend talks to ``/var/run/docker.sock`` (HTTP over a unix socket, stdlib
only — no docker-py). Used to start GPU model containers on demand and stop
them shortly after a task finishes, so a single GPU can be time-shared.

Per-service MODE (persisted as JSON on the shared volume):
- ``off``        — never auto-start; treated as disabled.
- ``mixed``      — start on demand, stop ~10s after a successful task.
- ``permanent``  — keep running (don't auto-stop).
"""
from __future__ import annotations

import asyncio
import http.client
import json
import logging
import os
import socket
from pathlib import Path

logger = logging.getLogger(__name__)

_SOCK = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
_MODE_FILE = Path(os.environ.get("SERVICE_MODES_FILE", "/storage/service_modes.json"))
_STOP_DELAY = float(os.environ.get("SERVICE_STOP_DELAY_SECONDS", "10"))

# Logical service -> container name + which compose service it maps to.
SERVICE_CONTAINERS: dict[str, str] = {
    "model-comfyui": "aivideo-model-comfyui-1",
    "model-wav2lip": "aivideo-model-wav2lip-1",
    "model-hallo": "aivideo-model-hallo-1",
    "model-musetalk": "aivideo-model-musetalk-1",
    "model-liveportrait": "aivideo-model-liveportrait-1",
    "model-echomimic": "aivideo-model-echomimic-1",
    "model-sadtalker": "aivideo-model-sadtalker-1",
    "model-tts-ro": "aivideo-model-tts-ro-1",
    "model-flux": "aivideo-model-flux-1",
}
# video provider_id -> docker service (for on-demand start at job creation).
VIDEO_PROVIDER_SERVICE: dict[str, str] = {
    "wav2lip": "model-wav2lip", "hallo": "model-hallo", "musetalk": "model-musetalk",
    "liveportrait": "model-liveportrait", "echomimic": "model-echomimic", "sadtalker": "model-sadtalker",
}
# GPU consumers — only ONE should run at a time on a single GPU. tts-ro is CPU.
GPU_SERVICES = {
    "model-comfyui", "model-wav2lip", "model-hallo", "model-musetalk",
    "model-liveportrait", "model-echomimic", "model-sadtalker", "model-flux",
}
# Internal readiness URLs (backend → container) to confirm the HTTP server is up.
_READY_URL = {
    "model-comfyui": "http://aivideo-model-comfyui-1:8188/system_stats",
    "model-wav2lip": "http://aivideo-model-wav2lip-1:8080/health",
    "model-hallo": "http://aivideo-model-hallo-1:8080/health",
    "model-musetalk": "http://aivideo-model-musetalk-1:8080/health",
    "model-liveportrait": "http://aivideo-model-liveportrait-1:8080/health",
    "model-echomimic": "http://aivideo-model-echomimic-1:8080/health",
    "model-sadtalker": "http://aivideo-model-sadtalker-1:8080/health",
    "model-tts-ro": "http://aivideo-model-tts-ro-1:8080/health",
    "model-flux": "http://aivideo-model-flux-1:8080/health",
}
VALID_MODES = ("off", "mixed", "permanent")
_DEFAULT_MODES = {
    "model-comfyui": "mixed",
    "model-wav2lip": "mixed",
    "model-hallo": "mixed",
    "model-musetalk": "mixed",
    "model-liveportrait": "mixed",
    "model-echomimic": "mixed",
    "model-sadtalker": "off",
    "model-tts-ro": "permanent",
    "model-flux": "off",
}


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float = 15.0):
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:  # type: ignore[override]
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._path)
        self.sock = s


def _docker(method: str, url: str, timeout: float = 30.0) -> tuple[int, bytes]:
    conn = _UnixHTTPConnection(_SOCK, timeout=timeout)
    try:
        conn.request(method, url)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


# --- modes (JSON on the shared volume) ------------------------------------

def load_modes() -> dict[str, str]:
    try:
        data = json.loads(_MODE_FILE.read_text())
        if isinstance(data, dict):
            return {**_DEFAULT_MODES, **{k: v for k, v in data.items() if v in VALID_MODES}}
    except Exception:
        pass
    return dict(_DEFAULT_MODES)


def set_mode(service: str, mode: str) -> dict[str, str]:
    if service not in SERVICE_CONTAINERS:
        raise ValueError(f"unknown service {service!r}")
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}")
    modes = load_modes()
    modes[service] = mode
    try:
        _MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MODE_FILE.write_text(json.dumps(modes))
    except Exception as exc:  # noqa: BLE001
        logger.warning("service modes persist failed: %s", exc)
    return modes


# --- container ops (best-effort; never raise into the request) ------------

def is_running(service: str) -> bool:
    name = SERVICE_CONTAINERS.get(service, service)
    try:
        st, body = _docker("GET", f"/containers/{name}/json", timeout=8)
        return st == 200 and bool(json.loads(body).get("State", {}).get("Running"))
    except Exception:
        return False


def start(service: str) -> bool:
    name = SERVICE_CONTAINERS.get(service, service)
    try:
        st, _ = _docker("POST", f"/containers/{name}/start", timeout=60)
        ok = st in (204, 304)
        logger.info("docker start %s -> %s", name, st)
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("docker start %s failed: %s", name, exc)
        return False


def stop(service: str, t: int = 3) -> bool:
    name = SERVICE_CONTAINERS.get(service, service)
    try:
        st, _ = _docker("POST", f"/containers/{name}/stop?t={t}", timeout=60)
        logger.info("docker stop %s -> %s", name, st)
        return st in (204, 304)
    except Exception as exc:  # noqa: BLE001
        logger.warning("docker stop %s failed: %s", name, exc)
        return False


def _http_ready(service: str) -> bool:
    url = _READY_URL.get(service)
    if not url:
        return True  # no probe defined → trust the running state
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=4) as r:
            return r.status < 500
    except Exception:
        return False


async def ensure_started(service: str, *, ready_timeout: float = 180.0) -> bool:
    """Start the service if its mode allows it (mixed/permanent), serialising
    the GPU: any OTHER running GPU service in 'mixed' mode is stopped first so
    VRAM is free. Then wait until the container is running AND its HTTP server
    answers (real readiness, not a fixed sleep). Returns True if usable."""
    modes = load_modes()
    mode = modes.get(service, "off")
    if mode == "off":
        return False

    # GPU serialisation — free VRAM by stopping other running mixed GPU services.
    if service in GPU_SERVICES:
        for other in GPU_SERVICES:
            if other == service:
                continue
            if modes.get(other) == "mixed" and await asyncio.to_thread(is_running, other):
                logger.info("gpu serialise: stopping %s before %s", other, service)
                await asyncio.to_thread(stop, other)

    if not await asyncio.to_thread(is_running, service):
        await asyncio.to_thread(start, service)

    # Wait for container running + HTTP readiness (cold start + model load).
    deadline = asyncio.get_event_loop().time() + ready_timeout
    while asyncio.get_event_loop().time() < deadline:
        if await asyncio.to_thread(is_running, service) and await asyncio.to_thread(_http_ready, service):
            logger.info("service %s ready", service)
            return True
        await asyncio.sleep(3)
    logger.warning("service %s not ready within %ss", service, ready_timeout)
    return False


def schedule_stop_if_mixed(service: str) -> None:
    """After a successful task, stop the container ~10s later if mode=mixed."""
    if load_modes().get(service) != "mixed":
        return

    async def _later() -> None:
        await asyncio.sleep(_STOP_DELAY)
        # re-check mode (operator may have flipped it meanwhile)
        if load_modes().get(service) == "mixed":
            await asyncio.to_thread(stop, service)

    try:
        asyncio.get_running_loop().create_task(_later())
    except RuntimeError:
        pass  # no loop (sync context) — skip


def catalog() -> list[dict]:
    modes = load_modes()
    return [
        {"service": s, "container": c, "mode": modes.get(s, "off"), "running": is_running(s)}
        for s, c in SERVICE_CONTAINERS.items()
    ]

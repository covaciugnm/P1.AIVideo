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
    "model-sadtalker": "aivideo-model-sadtalker-1",
    "model-tts-ro": "aivideo-model-tts-ro-1",
    "model-flux": "aivideo-model-flux-1",
}
VALID_MODES = ("off", "mixed", "permanent")
_DEFAULT_MODES = {
    "model-comfyui": "mixed",
    "model-wav2lip": "mixed",
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


async def ensure_started(service: str) -> bool:
    """Start the service if its mode allows it (mixed/permanent). Waits for the
    container to report running + a short warmup. Returns True if usable."""
    mode = load_modes().get(service, "off")
    if mode == "off":
        return False
    if is_running(service):
        return True
    await asyncio.to_thread(start, service)
    # wait for running state (up to ~40s)
    for _ in range(20):
        if await asyncio.to_thread(is_running, service):
            await asyncio.sleep(3)  # brief warmup for the HTTP server
            return True
        await asyncio.sleep(2)
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

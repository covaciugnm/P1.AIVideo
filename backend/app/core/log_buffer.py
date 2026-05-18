"""Phase 13 — in-memory backend log ring buffer.

Captures every stdlib ``logging`` record emitted by the FastAPI process
into a bounded deque so the operator UI can render a live "Backend"
tab in the right sidebar without having to ``docker logs -f``.

Design notes:

- Single deque per process; thread-safe via a stdlib ``Lock``. A worker
  process per uvicorn worker is fine — each has its own buffer.
- Capacity is bounded (`max_records`) so a long-lived backend cannot
  leak memory. Old records are silently dropped when the cap is hit.
- The handler is attached to the **root** logger at startup. Existing
  loggers (uvicorn, FastAPI, alembic) inherit the handler automatically.
- The serialized shape is intentionally tiny so the SSE / poll endpoint
  can stream them with minimal CPU.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any, Deque, Iterable

_MAX_RECORDS_DEFAULT = 1000


@dataclass
class BackendLogRecord:
    seq: int
    ts: float
    level: str
    logger: str
    message: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _BackendLogBuffer:
    def __init__(self, max_records: int = _MAX_RECORDS_DEFAULT) -> None:
        self._buf: Deque[BackendLogRecord] = deque(maxlen=max_records)
        self._lock = threading.Lock()
        self._seq = 0

    def append(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        # Carry common structured attrs the handler may attach
        extra: dict[str, Any] = {}
        for key in ("job_id", "character_id", "provider_id", "stage", "phase"):
            value = getattr(record, key, None)
            if value is not None:
                extra[key] = value
        with self._lock:
            self._seq += 1
            self._buf.append(
                BackendLogRecord(
                    seq=self._seq,
                    ts=record.created,
                    level=record.levelname,
                    logger=record.name,
                    message=msg,
                    extra=extra,
                )
            )

    def snapshot(self, since_seq: int | None = None, limit: int = 200) -> list[BackendLogRecord]:
        with self._lock:
            items = list(self._buf)
        if since_seq is not None:
            items = [r for r in items if r.seq > since_seq]
        if limit and len(items) > limit:
            items = items[-limit:]
        return items

    def latest_seq(self) -> int:
        with self._lock:
            return self._seq


_BUFFER: _BackendLogBuffer | None = None


def get_buffer() -> _BackendLogBuffer:
    global _BUFFER
    if _BUFFER is None:
        _BUFFER = _BackendLogBuffer()
    return _BUFFER


class _BufferHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            get_buffer().append(record)
        except Exception:
            # Never let logging crash the request flow.
            pass


def install(level: int = logging.INFO) -> None:
    """Attach the ring-buffer handler AND a stdout StreamHandler so
    every log line shows up both in the sidebar's "Backend" tab AND
    in ``docker compose logs backend``. Idempotent."""
    import sys

    root = logging.getLogger()

    # Force root to let INFO through. Uvicorn's default leaves root at
    # WARNING with zero handlers attached, so app logger output goes
    # nowhere by default.
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)

    # 1. Ring-buffer handler for the sidebar endpoint.
    if not any(isinstance(h, _BufferHandler) for h in root.handlers):
        bh = _BufferHandler()
        bh.setLevel(level)
        root.addHandler(bh)

    # 2. Stdout StreamHandler so the same lines hit ``docker compose logs``.
    if not any(
        isinstance(h, logging.StreamHandler)
        and getattr(h, "_p1aivideo_stdout", False)
        for h in root.handlers
    ):
        sh = logging.StreamHandler(stream=sys.stdout)
        sh.setLevel(level)
        sh.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s.%(msecs)03d %(levelname)-5s %(name)s :: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        sh._p1aivideo_stdout = True  # type: ignore[attr-defined]
        root.addHandler(sh)

    # Make sure our app loggers themselves let INFO through. (uvicorn
    # has its own handlers; we leave those alone.)
    for name in ("app", "app.main", "app.api", "app.services", "app.request"):
        lg = logging.getLogger(name)
        if lg.level == logging.NOTSET or lg.level > level:
            lg.setLevel(level)
        lg.propagate = True

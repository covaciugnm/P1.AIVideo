"""Image-generation circuit breaker: stop after N consecutive failures."""
from __future__ import annotations

import uuid

import pytest

from app.services import character_image_service as svc
from app.services.image_providers import ProviderUnavailableError


@pytest.fixture(autouse=True)
def _reset_circuit():
    svc._circuit.clear()
    yield
    svc._circuit.clear()


def test_guard_allows_until_threshold(monkeypatch):
    monkeypatch.setattr(svc, "_CB_MAX", 5)
    cid = uuid.uuid4()
    # 4 failures: still allowed
    for _ in range(4):
        svc._cb_record_failure(cid)
        svc._cb_guard(cid)  # no raise
    # 5th failure opens the circuit
    svc._cb_record_failure(cid)
    with pytest.raises(ProviderUnavailableError) as ei:
        svc._cb_guard(cid)
    assert ei.value.error_code == "circuit_open"


def test_success_resets_counter(monkeypatch):
    monkeypatch.setattr(svc, "_CB_MAX", 5)
    cid = uuid.uuid4()
    for _ in range(4):
        svc._cb_record_failure(cid)
    svc._cb_record_success(cid)  # reset
    # a fresh streak is allowed again
    for _ in range(4):
        svc._cb_record_failure(cid)
        svc._cb_guard(cid)


def test_other_character_unaffected(monkeypatch):
    monkeypatch.setattr(svc, "_CB_MAX", 5)
    a, b = uuid.uuid4(), uuid.uuid4()
    for _ in range(5):
        svc._cb_record_failure(a)
    with pytest.raises(ProviderUnavailableError):
        svc._cb_guard(a)
    svc._cb_guard(b)  # b is independent → no raise

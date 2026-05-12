"""Compliance-token mint + verify.

Phase 2 uses a lightweight HMAC-signed envelope:

    <base64(payload_json)>.<hex(hmac_sha256(payload_json, key))>

Why HMAC and not JWT? Keeping the dep tree small — JWT would pull in
crypto libraries we don't otherwise need in Phase 2. Phase 5+ can swap to
asymmetric JWT signing for federated verification.

The token's claims are `common.schemas.ComplianceTokenClaims`. LipSync (and
any other token-gated stage) must call `verify_token()` before doing work.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

from common.exceptions import ComplianceTokenError
from common.schemas import ComplianceTokenClaims


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload_bytes: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return sig


def mint_token(claims: ComplianceTokenClaims, secret: str) -> str:
    """Serialize + sign claims into a compact token string."""
    if not secret:
        raise ComplianceTokenError("compliance_signing_key is empty")
    payload_json = claims.model_dump_json()
    payload_bytes = payload_json.encode("utf-8")
    encoded = _b64url_encode(payload_bytes)
    sig = _sign(payload_bytes, secret)
    return f"{encoded}.{sig}"


def verify_token(
    token: str,
    secret: str,
    *,
    expected_job_id: str | None = None,
    now: datetime | None = None,
) -> ComplianceTokenClaims:
    """Verify signature + expiry; optionally match the job id.

    Raises `ComplianceTokenError` on any failure. Returns the parsed claims
    on success.
    """
    if not token or "." not in token:
        raise ComplianceTokenError("malformed token")
    encoded, sig = token.rsplit(".", 1)
    try:
        payload_bytes = _b64url_decode(encoded)
    except Exception as exc:  # noqa: BLE001
        raise ComplianceTokenError("token payload not base64") from exc

    expected_sig = _sign(payload_bytes, secret)
    if not hmac.compare_digest(sig, expected_sig):
        raise ComplianceTokenError("signature mismatch")

    try:
        claims_dict = json.loads(payload_bytes)
        claims = ComplianceTokenClaims.model_validate(claims_dict)
    except Exception as exc:  # noqa: BLE001
        raise ComplianceTokenError(f"claims invalid: {exc}") from exc

    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    # The token's datetimes are written naive UTC by mint_token; normalize.
    expires = claims.expires_at
    if expires.tzinfo is not None:
        expires = expires.astimezone(timezone.utc).replace(tzinfo=None)
    if current >= expires:
        raise ComplianceTokenError("token expired")

    if expected_job_id is not None and claims.job_id != expected_job_id:
        raise ComplianceTokenError("token job_id mismatch")

    return claims

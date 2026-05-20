"""Optional identity drift scoring — Phase IG-5.

Computes cosine similarity between the canonical face reference and a
generated image using a local ArcFace embedding (InsightFace). This is
**off by default** (``FACE_EMBEDDING_ENABLED=false``) because:

  * the InsightFace pretrained models are non-commercial license, and
  * the dependency (onnxruntime + insightface) is heavy for the backend
    image and is better isolated in a dedicated worker.

When disabled (or when the dependency / model is unavailable) every call
returns ``(None, False)`` — the caller stores a null score and continues.
Never raises into the generation path.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return os.environ.get("FACE_EMBEDDING_ENABLED", "false").lower() in (
        "true", "1", "yes",
    )


def _warn_threshold() -> float:
    try:
        return float(os.environ.get("FACE_SIMILARITY_WARNING_THRESHOLD", "0.35"))
    except ValueError:
        return 0.35


def score_identity(
    reference_image_path: str, generated_image_path: str
) -> tuple[float | None, bool]:
    """Return ``(cosine_similarity, drift_warning)``.

    ``(None, False)`` when scoring is disabled/unavailable. ``drift_warning``
    is True when the score is below ``FACE_SIMILARITY_WARNING_THRESHOLD``.
    Thresholds ship as conservative defaults and MUST be calibrated against
    your model before they gate anything in production.
    """
    if not is_enabled():
        return None, False
    try:
        import numpy as np  # noqa: F401
        from insightface.app import FaceAnalysis  # type: ignore
    except Exception as exc:  # noqa: BLE001 — optional dep
        logger.warning("face scoring disabled — dependency unavailable: %s", exc)
        return None, False
    try:
        import cv2  # type: ignore
        import numpy as np

        app = FaceAnalysis(
            name=os.environ.get("FACE_EMBEDDING_MODEL", "antelopev2"),
            root=os.environ.get("FACE_EMBEDDING_ROOT", "/models/insightface"),
        )
        app.prepare(ctx_id=-1)  # CPU

        def _embed(path: str):
            img = cv2.imread(path)
            if img is None:
                return None
            faces = app.get(img)
            if not faces:
                return None
            v = faces[0].normed_embedding
            return v / (np.linalg.norm(v) + 1e-9)

        a = _embed(reference_image_path)
        b = _embed(generated_image_path)
        if a is None or b is None:
            return None, False
        sim = float(np.dot(a, b))
        return sim, sim < _warn_threshold()
    except Exception as exc:  # noqa: BLE001 — never break generation
        logger.warning("face scoring failed (non-fatal): %s", exc)
        return None, False

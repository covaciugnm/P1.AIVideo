"""policy_gate — intake compliance gate.

Phase 1 logic: structural validation of consent/synthetic-person flags +
keyword-level scan of the brief against configs/policies/banned_topics.yaml.
No ML classifier yet; that lands in Phase 2.

This module is intentionally framework-free. It takes a frozen view of the
job's brief and returns a decision. The orchestrator (or any caller) owns
the side effects (DB row, event emission).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Resolve to <repo>/configs/policies/banned_topics.example.yaml by default.
# Operators copy this to banned_topics.yaml; if that file exists we prefer it.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_POLICY_DIR = _REPO_ROOT / "configs" / "policies"
_DEFAULT_POLICY_PATH = _POLICY_DIR / "banned_topics.yaml"
_FALLBACK_POLICY_PATH = _POLICY_DIR / "banned_topics.example.yaml"


@dataclass(frozen=True)
class JobBriefView:
    """A minimal, framework-free snapshot of a job's brief.

    Decoupled from the SQLAlchemy model so the gate can be called from any
    context (API service, orchestrator handler, unit test) without dragging
    in DB or ORM dependencies.
    """

    job_id: str
    brief: str
    synthetic_person_confirmed: bool
    consent_confirmed: bool
    watermark_required: bool
    c2pa_required: bool


@dataclass
class PolicyGateDecision:
    accepted: bool
    reasons: list[str] = field(default_factory=list)


def _select_policy_path(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.exists() else None
    if _DEFAULT_POLICY_PATH.exists():
        return _DEFAULT_POLICY_PATH
    if _FALLBACK_POLICY_PATH.exists():
        return _FALLBACK_POLICY_PATH
    return None


def _load_block_keywords(path: Path) -> list[str]:
    """Read block-severity keyword lists from the policy YAML.

    Phase 1 only does literal-keyword matching. The semantic descriptions
    in the YAML are for human readers; ML classification lands in Phase 2.
    """
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    keywords: list[str] = []
    for rule in data.get("rules", []) or []:
        if rule.get("severity") != "block":
            continue
        for kw in rule.get("keywords", []) or []:
            keywords.append(str(kw).lower())
    return keywords


def policy_gate(
    job: JobBriefView,
    policy_path: Path | None = None,
) -> PolicyGateDecision:
    """Run the intake policy gate against a job's brief.

    Reject conditions:
    - synthetic_person_confirmed is false
    - consent_confirmed is false
    - watermark_required is false
    - c2pa_required is false
    - brief contains a literal banned-topic keyword (case-insensitive, word boundary)

    Returns:
        PolicyGateDecision(accepted=bool, reasons=[...])
        On accept, `reasons` is empty.
    """
    reasons: list[str] = []

    if not job.synthetic_person_confirmed:
        reasons.append("synthetic_person_confirmed must be true")
    if not job.consent_confirmed:
        reasons.append("consent_confirmed must be true")
    if not job.watermark_required:
        reasons.append("watermark_required must be true")
    if not job.c2pa_required:
        reasons.append("c2pa_required must be true")

    path = _select_policy_path(policy_path)
    if path is not None:
        keywords = _load_block_keywords(path)
        if keywords:
            text = job.brief.lower()
            for kw in keywords:
                # Word-boundary match; whitespace tolerated for multi-word keywords.
                pattern = re.escape(kw).replace(r"\ ", r"\s+")
                if re.search(rf"(?:^|\W){pattern}(?:$|\W)", text):
                    # Don't leak the full list back — one is enough to reject.
                    reasons.append(f"brief contains banned keyword: {kw!r}")
                    break

    return PolicyGateDecision(accepted=(len(reasons) == 0), reasons=reasons)

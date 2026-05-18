"""Phase 15F — lightweight Romanian → English translator for image gen prompts.

Diffusion models (FLUX, SDXL, SD3.5) are trained almost exclusively on
English captions; a Romanian prompt gets interpreted as noise and yields
unrelated output. When the operator UI is in Romanian we transparently
translate the prompt before forwarding it to the wrapper, and log both
the original and the translated text.

Translation backend: the public Google Translate endpoint at
``translate.googleapis.com`` (no API key needed). It's rate-limited for
abuse but fine for a single-operator dashboard. On failure we return
the original text so the request still goes through (with predictable
poor quality).
"""
from __future__ import annotations

import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


_ROMANIAN_DIACRITICS = set("ăâîșțĂÂÎȘȚşţŞŢ")
# Common Romanian function words / verbs unlikely to appear in English prompts.
_ROMANIAN_HINTS = {
    "cu", "si", "în", "in", "de", "la", "pe", "fă", "fa",
    "pentru", "este", "sunt", "vrea", "vrei", "vreau",
    "imagine", "imagini", "poză", "pozele", "același",
    "aceeași", "acelaș", "persoana", "persoane", "fata",
    "imbracat", "îmbrăcat", "îmbrăcată", "imbracata",
    "genereaza", "generează", "ploaie", "vremea", "ploios",
    "ploioasă", "rece", "cald", "frumos", "frumoasă",
}


def looks_romanian(text: str) -> bool:
    """Heuristic: any Romanian diacritic OR ≥2 common RO function words."""
    if not text:
        return False
    if any(c in _ROMANIAN_DIACRITICS for c in text):
        return True
    words = set(w.lower().strip(",.!?;:") for w in text.split())
    return len(words & _ROMANIAN_HINTS) >= 2


def translate_ro_to_en(text: str, *, timeout: float = 5.0) -> str:
    """Return English translation of a Romanian prompt.

    Synchronous (uses stdlib urllib so we don't add an async dep here).
    Returns the original text on any failure — never raises.
    """
    if not text or not text.strip():
        return text
    url = (
        "https://translate.googleapis.com/translate_a/single"
        "?client=gtx&sl=ro&tl=en&dt=t&q=" + urllib.parse.quote(text)
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            import json
            payload = json.loads(resp.read())
        # payload[0] is a list of segment-tuples: [[translated, original, ...], ...]
        translated = "".join(seg[0] for seg in payload[0] if seg and seg[0])
        return translated.strip() or text
    except Exception as exc:  # noqa: BLE001 — defensive
        logger.warning("translate_ro_to_en failed: %s — passing original", exc)
        return text


def maybe_translate_for_image_gen(text: str | None, *, force: bool = False) -> tuple[str | None, bool]:
    """Translate iff the text looks Romanian (or force=True).

    Returns (text_or_translated, was_translated).
    """
    if not text:
        return text, False
    if not force and not looks_romanian(text):
        return text, False
    translated = translate_ro_to_en(text)
    return translated, translated.strip() != text.strip()

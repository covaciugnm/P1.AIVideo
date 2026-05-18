"""Mock image provider — Phase 12.

Generates a deterministic PNG with the operator's prompt rendered as
text. No external dependencies (stdlib ``struct`` + ``zlib`` only).
Used by tests, CI and the default no-credentials dev path.
"""
from __future__ import annotations

import hashlib
import struct
import zlib

from app.services.image_providers.base import (
    ImageGenerationInput,
    ImageGenerationResult,
    ImageProvider,
    ProviderCapabilities,
    ProviderHealth,
)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    chunk = tag + data
    crc = zlib.crc32(chunk) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", crc)


def _generate_solid_color_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Produce a tiny PNG filled with ``rgb``.

    No Pillow dependency — this keeps the mock CI-safe even when image
    libs are missing.
    """
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    # PNG scanline: filter byte (0) + raw RGB row
    row = bytes(rgb) * width
    raw = b"".join(b"\x00" + row for _ in range(height))
    idat = zlib.compress(raw, 9)
    return (
        sig
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


class MockImageProvider(ImageProvider):
    provider_id = "mock"
    display_name = "Mock image generator (deterministic placeholder PNG)"
    default_model = "mock-v1"
    capabilities = ProviderCapabilities(
        text_to_image=True,
        image_to_image=True,
        reference_image=True,
        multi_reference=False,
        negative_prompt=True,
        seed=True,
        local=True,
        api=False,
    )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status="available", notes="Mock provider — always healthy.")

    async def generate_text_to_image(
        self, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        return self._produce(request)

    async def generate_image_to_image(
        self, request: ImageGenerationInput
    ) -> ImageGenerationResult:
        # Mock image-to-image — same payload, different rgb seed.
        return self._produce(request)

    def _produce(self, request: ImageGenerationInput) -> ImageGenerationResult:
        # Deterministic colour from prompt + seed so the same input
        # always yields the same PNG. Tests can assert on this.
        digest = hashlib.sha256(
            (
                (request.prompt or "")
                + "|"
                + (request.model_id or "")
                + "|"
                + str(request.seed or 0)
                + "|"
                + (request.reference_image_path or "")
            ).encode("utf-8")
        ).digest()
        rgb = (digest[0], digest[1], digest[2])
        # Cap the synthesised canvas so tests don't blow up on huge
        # inputs while still respecting the operator's aspect ratio.
        max_dim = 256
        w = max(8, min(max_dim, request.width))
        h = max(8, min(max_dim, request.height))
        png = _generate_solid_color_png(w, h, rgb)
        return ImageGenerationResult(
            image_bytes=png,
            mime_type="image/png",
            width=w,
            height=h,
            seed=request.seed,
            model_id=request.model_id or self.default_model,
            provider_metadata={
                "provider_id": self.provider_id,
                "mock_rgb": list(rgb),
                "deterministic": True,
                "prompt_sha256": digest.hex(),
            },
        )

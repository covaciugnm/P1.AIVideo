"""Stdlib-only image validation + dimension extraction.

Phase 3E scope:
- Parse PNG / JPEG / WebP headers far enough to extract ``(width, height)``.
- Verify file existence, size limit, declared mime_type.
- Compute SHA-256 of the file contents.

No Pillow / OpenCV / imageio / numpy. Just file IO + bit-twiddling.

The parsers are deliberately minimal — they read only the bytes needed
for dimensions, NOT the full image. If a file claims one mime_type but
its header doesn't match, the parser raises ``ValueError`` (an
actionable error rather than silently accepting). This is enough for
Phase 3E's contract: validate the metadata operators declared, do not
perform any image processing.

WebP support covers the three container variants:
- VP8X (extended) — explicit width / height in the chunk header.
- VP8L (lossless) — packed bits after a 0x2F signature byte.
- VP8  (lossy)    — 14-bit width / height after the 0x9d01 2a signature.
The parser walks RIFF chunks until it finds one of those.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path


_ALLOWED_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


@dataclass(frozen=True)
class ImageMetadata:
    path: Path
    size_bytes: int
    mime_type: str
    format: str  # "png" | "jpeg" | "webp"
    width: int
    height: int
    checksum_sha256: str


# ---------------------------------------------------------------------------
# Per-format header parsers
# ---------------------------------------------------------------------------


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _parse_png(data: bytes) -> tuple[int, int]:
    if len(data) < 24:
        raise ValueError("invalid PNG header: truncated")
    if data[:8] != _PNG_SIGNATURE:
        raise ValueError("invalid PNG header: bad signature")
    if data[12:16] != b"IHDR":
        raise ValueError("invalid PNG header: IHDR missing")
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid PNG dimensions: {width}x{height}")
    return width, height


def _parse_jpeg(stream) -> tuple[int, int]:
    """Walk JPEG markers until we find an SOFn segment.

    SOFn = 0xFF, 0xC0..0xCF (excluding 0xC4 DHT, 0xC8 JPG, 0xCC DAC).
    SOFn payload: 2 bytes length, 1 byte precision, 2 bytes height,
    2 bytes width (in that order).
    """
    soi = stream.read(2)
    if soi != b"\xff\xd8":
        raise ValueError("invalid JPEG header: missing SOI")
    while True:
        # Markers are 0xFF 0xXX; multiple 0xFF can appear as padding.
        b = stream.read(1)
        if not b:
            raise ValueError("invalid JPEG header: truncated before SOF")
        if b != b"\xff":
            raise ValueError("invalid JPEG header: marker out of sync")
        marker = stream.read(1)
        if not marker:
            raise ValueError("invalid JPEG header: truncated after FF")
        m = marker[0]
        if m == 0xFF:
            # Fill byte — keep scanning.
            continue
        if m in (0xD8, 0xD9):
            raise ValueError("invalid JPEG header: encountered SOI/EOI mid-stream")
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            length_bytes = stream.read(2)
            if len(length_bytes) < 2:
                raise ValueError("invalid JPEG header: SOFn truncated")
            stream.read(1)  # precision
            h_bytes = stream.read(2)
            w_bytes = stream.read(2)
            if len(h_bytes) < 2 or len(w_bytes) < 2:
                raise ValueError("invalid JPEG header: SOFn dimensions truncated")
            height = int.from_bytes(h_bytes, "big")
            width = int.from_bytes(w_bytes, "big")
            if width <= 0 or height <= 0:
                raise ValueError(f"invalid JPEG dimensions: {width}x{height}")
            return width, height
        # Segments with length: skip them.
        length_bytes = stream.read(2)
        if len(length_bytes) < 2:
            raise ValueError("invalid JPEG header: truncated segment length")
        length = int.from_bytes(length_bytes, "big")
        if length < 2:
            raise ValueError(f"invalid JPEG header: negative segment payload ({length})")
        stream.seek(length - 2, 1)


def _parse_webp(data: bytes) -> tuple[int, int]:
    """Walk RIFF chunks looking for VP8X / VP8L / VP8 and return dimensions."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("invalid WebP header: missing RIFF/WEBP signature")

    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        chunk_size = int.from_bytes(data[pos + 4:pos + 8], "little")
        payload_start = pos + 8
        payload_end = payload_start + chunk_size

        if chunk_id == b"VP8X":
            # 1 byte flags + 3 bytes reserved + 3 bytes (width-1) LE + 3 bytes (height-1) LE.
            if len(data) < payload_start + 10:
                raise ValueError("invalid WebP VP8X chunk: truncated")
            w_bytes = data[payload_start + 4:payload_start + 7] + b"\x00"
            h_bytes = data[payload_start + 7:payload_start + 10] + b"\x00"
            width = struct.unpack("<I", w_bytes)[0] + 1
            height = struct.unpack("<I", h_bytes)[0] + 1
            if width <= 0 or height <= 0:
                raise ValueError(f"invalid WebP VP8X dimensions: {width}x{height}")
            return width, height

        if chunk_id == b"VP8 ":
            # Lossy: skip 3 bytes (frame tag) + 3 bytes signature, then 4 bytes width|height.
            sig_start = payload_start + 3
            if len(data) < sig_start + 7:
                raise ValueError("invalid WebP VP8 chunk: truncated")
            if data[sig_start:sig_start + 3] != b"\x9d\x01\x2a":
                raise ValueError("invalid WebP VP8 chunk: missing start signature")
            wh_start = sig_start + 3
            width = int.from_bytes(data[wh_start:wh_start + 2], "little") & 0x3FFF
            height = int.from_bytes(data[wh_start + 2:wh_start + 4], "little") & 0x3FFF
            if width <= 0 or height <= 0:
                raise ValueError(f"invalid WebP VP8 dimensions: {width}x{height}")
            return width, height

        if chunk_id == b"VP8L":
            # Lossless: signature byte 0x2F, then 4 bytes packed:
            # bits[0..13]   = width - 1
            # bits[14..27]  = height - 1
            if len(data) < payload_start + 5:
                raise ValueError("invalid WebP VP8L chunk: truncated")
            if data[payload_start] != 0x2F:
                raise ValueError("invalid WebP VP8L chunk: missing 0x2F signature")
            packed = int.from_bytes(data[payload_start + 1:payload_start + 5], "little")
            width = (packed & 0x3FFF) + 1
            height = ((packed >> 14) & 0x3FFF) + 1
            if width <= 0 or height <= 0:
                raise ValueError(f"invalid WebP VP8L dimensions: {width}x{height}")
            return width, height

        # Chunks are word-aligned: payload pads to even length.
        advance = chunk_size + (chunk_size & 1)
        pos = payload_start + advance

    raise ValueError("invalid WebP file: no VP8 / VP8L / VP8X chunk found")


# ---------------------------------------------------------------------------
# Hashing + top-level dispatch
# ---------------------------------------------------------------------------


def _compute_sha256(path: Path, *, chunk_size: int = 64 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _format_from_mime(mime: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpeg",
        "image/webp": "webp",
    }[mime]


def validate_and_inspect_image(
    path: str | Path,
    *,
    mime_type: str,
    max_size_bytes: int | None = None,
    min_width: int | None = None,
    min_height: int | None = None,
) -> ImageMetadata:
    """Open, inspect, and checksum an image file.

    Raises ``ValueError`` on:

    - File does not exist or is not a regular file.
    - ``mime_type`` is not in the supported set.
    - File size exceeds ``max_size_bytes`` (if specified).
    - Header is unparseable as the declared mime_type.
    - Width or height is below the configured minimum.

    Returns ``ImageMetadata`` with extracted ``(width, height)``,
    size, mime_type, and SHA-256.
    """
    if mime_type not in _ALLOWED_MIME_TYPES:
        raise ValueError(
            f"mime_type must be one of {sorted(_ALLOWED_MIME_TYPES)}; got {mime_type!r}"
        )

    p = Path(path)
    if not p.exists():
        raise ValueError(f"image file not found: {path!s}")
    if not p.is_file():
        raise ValueError(f"image path is not a regular file: {path!s}")

    size = p.stat().st_size
    if max_size_bytes is not None and size > max_size_bytes:
        raise ValueError(
            f"image file size {size} exceeds IMAGE_MAX_FILE_SIZE_BYTES limit {max_size_bytes}"
        )

    if mime_type == "image/png":
        with p.open("rb") as f:
            head = f.read(24)
        width, height = _parse_png(head)
    elif mime_type == "image/jpeg":
        with p.open("rb") as f:
            width, height = _parse_jpeg(f)
    else:  # image/webp
        with p.open("rb") as f:
            # WebP chunk walk needs the file in memory up to the chunk we
            # want; 64 KB is plenty for the small headers we care about.
            head = f.read(65536)
        width, height = _parse_webp(head)

    if min_width is not None and width < min_width:
        raise ValueError(
            f"image width {width} below configured IMAGE_MIN_WIDTH {min_width}"
        )
    if min_height is not None and height < min_height:
        raise ValueError(
            f"image height {height} below configured IMAGE_MIN_HEIGHT {min_height}"
        )

    return ImageMetadata(
        path=p,
        size_bytes=size,
        mime_type=mime_type,
        format=_format_from_mime(mime_type),
        width=width,
        height=height,
        checksum_sha256=_compute_sha256(p),
    )

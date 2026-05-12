# Disclosure Requirements

Every reel produced by P1.AIVideo carries three layers of disclosure. All three are mandatory; the Publisher agent refuses to emit an artifact missing any of them.

## 1. Visible overlay (burned-in)

- **Text:** `DISCLOSURE_OVERLAY_TEXT` (default `"AI-generated"`).
- **Position:** `DISCLOSURE_OVERLAY_POSITION` (default `bottom_left`).
- **Size:** minimum 4% of frame height (`DISCLOSURE_OVERLAY_MIN_HEIGHT_PCT`).
- **Style:** high-contrast against typical content; semi-opaque background plate behind the text for legibility.
- **Visibility test:** OCR at QC must read the disclosure text on a sampled set of frames; fail the QC if not.

## 2. C2PA manifest (Content Credentials)

- Embedded in the MP4 using `c2patool` against the signing identity in `configs/c2pa/`.
- Declares: `claim_generator = "P1.AIVideo/v1"`, AI-generated assertion, model versions used (per stage), producer identity, and content hash.
- Verifier link: any C2PA-capable verifier (e.g., the Content Authenticity Initiative inspector) should resolve the manifest cleanly.

## 3. XMP / EXIF flag

- `XMP-dc:Source = "AI-generated"`
- `XMP-xmpRights:Marked = "True"`
- Custom namespace block recording the pipeline name and version.

## Verification checks (QC)

- **OCR check** on N sampled frames — must find the disclosure text.
- **C2PA verify** — `c2patool verify reel_final.mp4` must succeed.
- **XMP probe** — `exiftool` reads back the expected fields.

If any of these fail, the Publisher refuses to publish and writes a `disclosure_failure` row to `audit_log`.

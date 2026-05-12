# assets/

Static assets used by the Editor agent. Every asset shipped here must have a verifiable license suitable for the project's commercial posture — see [`LICENSES.md`](LICENSES.md).

## Layout

```
assets/
├── fonts/                 # subtitle + overlay fonts (license-cleared)
├── music/                 # music beds (license-cleared)
├── broll/                 # synthetic or licensed B-roll clips
└── disclosure_overlays/   # PNG overlays + animated variants
```

## Hard rules

- No user-uploaded media here unless the upload flow itself enforces license proof.
- No real-person photography (the system never depicts real people).
- Each subdirectory has its own per-file license listing in `LICENSES.md`.

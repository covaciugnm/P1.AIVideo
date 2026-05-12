# SadTalker Provider (v1 default)

Default implementation of the LipSync adapter. Status: **planned, not yet coded.**

## Source

- Repo: <https://github.com/OpenTalker/SadTalker>
- License: Apache-2.0 (verify at integration time; mirror in `models/MODEL_CARDS.md`).

## Required assets

Populate under `$SADTALKER_CHECKPOINTS_DIR` (default `/models/lipsync/sadtalker/checkpoints`) and `$SADTALKER_GFPGAN_DIR` (`/models/lipsync/sadtalker/gfpgan`). Exact list and sha256 hashes go into `models/MODEL_CARDS.md` and the provider's `required_assets()` once implemented.

Typical set (illustrative; verify against upstream at impl time):

- `mapping_00109-model.pth.tar`
- `mapping_00229-model.pth.tar`
- `SadTalker_V0.0.2_256.safetensors`
- `SadTalker_V0.0.2_512.safetensors`
- `GFPGANv1.4.pth`

## Inputs / outputs

Conforms to the `LipSyncRequest` / `LipSyncResult` contract in [`docs/architecture/lipsync-adapter.md`](../../../../docs/architecture/lipsync-adapter.md).

## GPU & performance notes

- ~6 GB peak VRAM at 256 px; ~10 GB at 512 px.
- 25 fps recommended for reel work.
- GFPGAN restoration pass produces noticeable sharpening but doubles wall time.

## Hard rules

- Refuses to run without a valid `compliance_token`.
- Refuses to start if any required asset is missing or fails sha256 verification.
- Does not download weights at runtime unless `ALLOW_MODEL_AUTODOWNLOAD=true`.

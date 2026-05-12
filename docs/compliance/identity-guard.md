# Identity Guard

The Identity Guard is a **negative filter**: it exists to reject generated faces that resemble real people. It is never used to *target* a real person.

## How it works

1. After the Face agent produces a portrait, embed it with a CLIP image encoder.
2. Run an approximate-nearest-neighbor search against a curated **public-figures embedding index** stored at `IDENTITY_GUARD_INDEX_PATH`.
3. If the top-k cosine similarity exceeds `IDENTITY_GUARD_THRESHOLD` (default `0.85`), reject the portrait.
4. The Face agent regenerates with a new seed. After N consecutive rejections, the job is failed with a `identity_guard_exhausted` reason.

## What goes into the index

- Photographs of public figures (politicians, celebrities, executives) sourced from licensed datasets.
- The index stores **embeddings only**, not the source photographs.
- The index is built and signed by an operator process; the production deployment loads it read-only.

## What does NOT go into the index

- Photographs of private individuals.
- Anything not lawful to embed for this purpose under the operator's jurisdiction.

## Testing

- **Negative tests:** a corpus of synthetic portraits must produce zero matches at the configured threshold.
- **Positive tests:** a curated celebrity-photo set must produce matches for every entry at the configured threshold (validates the index loaded correctly).
- Both run in `tests/integration/identity_guard/` and gate CI.

## Failure handling

- A QC-time match (sampled frames of the final reel) is a hard fail. The artifact is quarantined and never reaches `reel_final.mp4`.
- A face-stage match triggers regeneration with a different seed.

## Refresh cadence

- Quarterly rebuild of the index from the source dataset.
- Out-of-band rebuild required when a major public figure enters the news cycle and is not yet in the index.

## Limitations (documented honestly)

- The guard is a similarity filter, not a guarantee. It can miss matches (false negatives) and is biased toward the demographics represented in the source dataset.
- For this reason it is one layer in a defense-in-depth approach (alongside the synthetic-only persona pipeline, the negative prompt in the Face agent, and policy gating).

# docker/

Dockerfiles per service and compose files. **Not yet implemented** — this scaffold documents the intended layout; concrete Dockerfiles + compose YAML land in Phase 0/1.

## Planned files

```
docker/
├── compose.dev.yml       # main dev stack (no GPU required for backend/frontend dev)
├── compose.gpu.yml       # overlay adding GPU reservations to agent-* services
├── compose.prod.yml      # production overrides (read-only mounts, smaller logs, etc.)
├── compose.test.yml      # mock model servers + ephemeral DB for integration tests
├── backend/Dockerfile    # FastAPI image
├── frontend/Dockerfile   # Next.js image
├── agents/
│   ├── orchestrator.Dockerfile
│   ├── scriptwriter.Dockerfile
│   ├── voice.Dockerfile          # CUDA base (optional GPU)
│   ├── face.Dockerfile           # CUDA base
│   ├── lipsync.Dockerfile        # CUDA base
│   ├── editor.Dockerfile         # python + ffmpeg
│   ├── qc.Dockerfile
│   ├── publisher.Dockerfile
│   └── compliance_officer.Dockerfile
└── models/
    └── vllm.Dockerfile           # model server image (vLLM)
```

## Conventions

- Multi-stage builds; final stages run as non-root with `USER 1000`.
- No model weights baked into images.
- `HEALTHCHECK` directives for every service.
- Pinned base image digests (not floating tags) in production builds.
- GPU access is declared in `compose.gpu.yml` only — base compose stays CPU-runnable.

See [`../docs/runbooks/gpu-docker.md`](../docs/runbooks/gpu-docker.md) for the GPU compose snippet.

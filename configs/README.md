# configs/

Project configuration that is **not** secret. Secrets live in `.env`.

## Layout

```
configs/
├── prompts/        # LLM system + user prompt templates per stage
├── voices/         # voice profile manifests (id → Piper/XTTS file paths + tone metadata)
├── personas/       # on-screen persona specs (age range, attire, lighting, framing)
├── policies/       # banned-topic rules and policy classifier config
└── c2pa/           # (gitignored) C2PA signing cert + key for the deployment
```

## Conventions

- All YAML/JSON files are schema-validated on backend startup.
- Editing `policies/banned_topics.yaml` requires the change-control flow in [`../docs/compliance/policy.md`](../docs/compliance/policy.md).
- Persona specs and voice profiles are referenced by stable id from briefs.

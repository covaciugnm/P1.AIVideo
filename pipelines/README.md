# pipelines/

Per-job DAG definitions consumed by the Orchestrator. One file per pipeline preset.

## Files

- `reel_default.yaml` — the default reel pipeline (full quality).
- `reel_fast.yaml` — a faster preset (skips heavy restoration, lower-res face).

## Format (sketch — finalized at impl time)

Each pipeline is a directed acyclic graph of stages. Edges declare dependencies. Each stage references an agent and a small parameter block.

```yaml
name: reel_default
schema_version: 1
budget:
  max_wall_minutes: 15
  max_gpu_minutes: 12
stages:
  - id: policy_gate
    agent: compliance_officer
    role: intake_gate
  - id: script
    agent: scriptwriter
    needs: [policy_gate]
  - id: voice
    agent: voice
    needs: [script]
  - id: face
    agent: face
    needs: [policy_gate]
  - id: lipsync
    agent: lipsync
    needs: [voice, face]
    params:
      backend: "${LIPSYNC_BACKEND}"
      fps: 25
  - id: editor
    agent: editor
    needs: [lipsync, script]
  - id: qc
    agent: qc
    needs: [editor]
  - id: publisher
    agent: publisher
    needs: [qc]
```

Hard rules:

- Every pipeline must include an intake `policy_gate` as the first stage.
- Every pipeline must end in `publisher`.
- Stages cannot bypass `qc` before `publisher`.

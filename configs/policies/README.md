# configs/policies/

Policy rulesets consumed by the Compliance Officer agent.

| File | Purpose |
|---|---|
| `banned_topics.example.yaml` | Example ruleset. Copy to `banned_topics.yaml` for your deployment. |
| `banned_topics.yaml` | (gitignored if it contains deployment-specific tuning) Active ruleset. |

Editing the active ruleset requires the change-control flow in [`../../docs/compliance/policy.md`](../../docs/compliance/policy.md).

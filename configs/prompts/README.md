# configs/prompts/

System + user prompt templates for the Scriptwriter (and any future LLM-using agents).

## Layout (planned)

```
prompts/
├── scriptwriter/
│   ├── system.md           # system prompt — isolated from user brief
│   ├── user_template.md    # user message template (parameterized)
│   └── examples/           # few-shot exemplars (curated, license-cleared)
└── compliance/
    └── classifier_system.md
```

## Conventions

- System prompts are versioned (e.g., `system.v3.md`). The active version is referenced by config.
- Templates use a strict variable set; CI tests that all referenced variables are populated.
- Prompts are reviewed by a compliance owner before activation.

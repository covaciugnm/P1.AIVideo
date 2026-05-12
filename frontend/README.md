# frontend/

Next.js dashboard. **Status:** to be implemented in Phase 4.

## Planned layout

```
frontend/
├── app/                # Next.js App Router pages
├── components/         # shared UI (forms, status badges, video player)
├── lib/                # API client, WebSocket client, auth helpers
└── public/             # static assets
```

## Pages (planned)

| Path | Purpose |
|---|---|
| `/` | Dashboard — recent jobs, queue health |
| `/jobs/new` | Brief submission form |
| `/jobs/[id]` | Live job progress + previews + per-stage logs |
| `/jobs/[id]/regenerate` | Regenerate a single stage |
| `/audit` | Audit log viewer (operator+) |
| `/admin/policies` | Policy ruleset viewer (admin) |

## Hard rules

- The frontend never embeds secrets. All requests are server-relayed.
- The frontend shows the disclosure overlay in previews too (no "preview hides the watermark" path).

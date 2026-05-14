# frontend/

Phase 4D operator dashboard. Next.js 14 App Router + TypeScript + vanilla
CSS modules. No Tailwind, no component libraries, no charting libs.

> **Settings → Backend API Base URL** is the runtime override that fixes
> "Failed to load jobs (HTTP 404)" when Docker publishes the backend on a
> non-default port (e.g. `BACKEND_PORT=8001`). Open the right sidebar →
> Settings → change the URL → click **Test backend connection**. The new
> value is persisted to `localStorage` (`aivideo:settings:v1`) and every
> subsequent API call uses it without a rebuild.

The UI is **metadata-only** — every screen reads from the FastAPI
backend's `/api/v1/*` JSON endpoints. Nothing in this folder embeds
secrets, talks to third-party services, or renders real generated media
(Phase 4B is metadata-and-disclosure-only).

## Layout

```
frontend/
├── app/                       # Next.js App Router pages
│   ├── globals.css            # CSS variables + base layout
│   ├── layout.tsx             # App shell (header / footer)
│   ├── page.tsx               # / — dashboard (recent jobs)
│   └── jobs/
│       ├── [jobId]/page.tsx   # /jobs/:id — live progress + artifacts
│       └── new/page.tsx       # /jobs/new — create job form
├── components/                # 12 shared UI components + .module.css each
└── lib/
    ├── api.ts                 # Typed API client (one fn per endpoint)
    ├── types.ts               # Mirrors backend Pydantic schemas
    ├── format.ts              # Date / bytes / duration helpers
    └── usePolling.ts          # Polling hook (used on the detail page)
```

## Configuration

Copy `.env.example` to `.env.local` and edit the base URL if your
backend isn't on `http://localhost:8000`:

```bash
cp .env.example .env.local
```

Only `NEXT_PUBLIC_API_BASE_URL` is needed.

## Commands

| Command | What it does |
|---|---|
| `npm install` | Install deps (Next.js 14, React 18, TypeScript). |
| `npm run dev` | Local dev server at `http://localhost:3000`. |
| `npm run build` | Production build (used by `make phase4b-test`). |
| `npm run lint` | `next lint --max-warnings 0` — zero-warning policy. |
| `npm run typecheck` | `tsc --noEmit`. |

You can also run these from the project root:

```bash
make frontend-install
make frontend-lint
make frontend-build
make frontend-check     # runs lint + build (also invoked by phase4b-test)
```

## Pages

| Path | Purpose |
|---|---|
| `/` | Dashboard. Polls `GET /api/v1/jobs` every 5 s; shows status, progress, current stage. |
| `/jobs/new` | Create-job form. Loads `GET /api/v1/config/ui-options` once; supports `tts` (inline script_text) and `provided_audio` (upload + reference) flows; optional `provided_image` face mode. Submits via `POST /api/v1/jobs/from-inputs`. |
| `/jobs/[jobId]` | Live job detail. Polls 7 endpoints in parallel every 3 s and renders progress, stage timeline, artifacts, compliance events, QC report, and final export. |

## Routes (Phase 4E)

| Path | Purpose |
|---|---|
| `/` | Dashboard — recent jobs polled on a configurable interval. |
| `/jobs` | Full jobs list with per-row View / Edit / Delete actions (inline confirm). |
| `/jobs/[jobId]` | Live job detail (progress, timeline, artifacts, compliance events, QC report, final export). |
| `/jobs/[jobId]/edit` | Metadata-only edit form (terminal jobs are read-only). |
| `/jobs/new` | Create-job wizard (brief, voice, optional face, compliance attestations). |
| `/uploads` | Standalone text / audio / image upload cards + session-scoped "Recent uploads". |
| `/settings` | Full-page mirror of the right-sidebar Settings panel. |

## Right sidebar (Phase 4D)

Persistent right-side panel on every page. Two tabs:

| Tab | What it does |
|---|---|
| **Logs** | Live frontend/backend/api/system events (filterable by level, source-mute via Settings, capped at `maxLogEntries`). Logs are local + in-memory — they disappear when you close the tab. |
| **Settings** | Backend API Base URL (+ Test connection), Frontend URL, polling interval, enable/disable auto polling, source toggles, max log entries, Reset to defaults. |

Collapsed (44 px rail) / expanded (320 px) state is persisted in
`localStorage` (`aivideo:sidebar:v1`).

## Hard rules (Phase 4B+4D)

- No real media preview / playback. Audio + image uploads show filename
  + size only — no `<audio>` / `<img>` element preview.
- No third-party scripts / fonts / icon libraries.
- No localStorage for compliance attestations — every consent flag is
  re-collected per job.
- The UI never embeds credentials. All requests cross the same
  origin-relative API base URL.

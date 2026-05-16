# Localization & subtitles — Phase 11A (re-do)

> **Scope:** P1.AIVideo speaks Romanian and English today. Every visible
> label in the dashboard and every help topic is translated. The
> architecture is built so adding a third language is a one-line config
> edit plus two dictionary files — never a component rewrite.

## Where the dictionaries live

| Purpose | File | Format |
|---|---|---|
| UI strings — English | `frontend/lib/i18n/dictionaries/en.ts` | TS object literal typed against `Dictionary` |
| UI strings — Romanian | `frontend/lib/i18n/dictionaries/ro.ts` | same shape, RO values |
| Help corpus — English | `frontend/lib/help/dictionaries/en.ts` | TS map of `HelpTopic` |
| Help corpus — Romanian | `frontend/lib/help/dictionaries/ro.ts` | same map, RO values |

Both UI files implement the exhaustive `Dictionary` interface
(`frontend/lib/i18n/types.ts`) — TypeScript refuses to compile if a key
is missing on either side. The Phase 11A test suite
(`tests/integration/test_phase11a_i18n_dictionaries.py`) re-asserts the
parity at runtime to catch hand-edits that bypass the typecheck.

The help corpora share a `HelpTopic` shape and a guaranteed set of 30
topic IDs. `getLocalizedHelpCorpus(lang)` (in
`frontend/lib/help/dictionaries/index.ts`) returns the right map; the
HelpOverlay consumes that.

## How language flips work

1. The operator changes the dropdown in the header (`LanguageSwitcher`).
2. `setLanguage(code)` in `LanguageContext.tsx` updates React state.
3. The state change re-renders every component that called `useT()`.
4. localStorage is updated for the next page load.
5. A best-effort PATCH to `/api/v1/settings/ui` saves the preference
   operator-wide (singleton DB row).
6. `<html lang="ro|en">` is updated for accessibility / spell-check.

There is **no page reload**. Text changes immediately because every
required component subscribes to the language context via `useT()`.

## Components covered

- Header nav + footer (`LocalizedNav`)
- All 7 pages (`/`, `/jobs`, `/jobs/new`, `/jobs/[id]`, `/jobs/[id]/edit`, `/uploads`, `/settings`)
- All 18 operator-facing components: `CreateJobForm`, `ArtifactTable`,
  `AudioPreview`, `VideoArtifactPreview`, `QcReportCard`, `FinalExportCard`,
  `JobRecoveryControls`, `UploadCard`, `SettingsPanel`,
  `ProvidersSection`, `CustomProvidersSection`, `ProviderTestPanel`,
  `LogsPanel`, `RightSidebar`, `SidebarTabs`, `HelpHint`, `HelpButton`,
  `HelpOverlay`
- All 4 error-glossary categories (`script_*`, `tts_*`, `video_*`,
  `provider_*`) — error codes use `t("errors.<code>")` in dictionaries
  and the help corpus.

## Supported languages

| Code | Native label | English label | Default? | RTL |
|---|---|---|---|---|
| `ro` | Română | Romanian | UI + video default | no |
| `en` | English | English | secondary | no |

The catalog lives in **one** place each side:

- **Backend:** [`backend/app/core/languages.py`](../../backend/app/core/languages.py) — `LANGUAGES` tuple. Validators in `backend/app/schemas/job.py` + `backend/app/schemas/uploads.py` check every operator-supplied language code against this list.
- **Frontend:** [`frontend/lib/i18n/types.ts`](../../frontend/lib/i18n/types.ts) — `SUPPORTED_LANGUAGE_CODES` + `LANGUAGE_META`.

The dashboard reads the backend catalog at runtime via
`GET /api/v1/config/languages`.

## Where the language preference lives

- **Operator-wide UI language** — `operator_settings` table (singleton
  row `id=1`). One row total today; ready to become per-user when auth
  ships.
- **Job-level video language** — `jobs.video_language` column. Default
  `ro` on every new job; validated at create + patch time.
- **Per-job subtitle settings** — `jobs.subtitle_*` columns + sidecar
  `ArtifactType.subtitle` rows.
- **Browser cache** — `localStorage["aivideo:ui-language"]` mirrors the
  DB value so the first paint isn't blocking on the backend round-trip.

## API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/config/languages` | Catalog + defaults. Read once on app boot; cache forever. |
| `GET` | `/api/v1/settings/ui` | Returns the singleton row. |
| `PATCH` | `/api/v1/settings/ui` | Updates `ui_language` / `default_video_language`. 422 on unsupported code. |

Job endpoints accept the following extra fields (all optional, all
schema-validated):

| Field | Default | Validation |
|---|---|---|
| `video_language` | `"ro"` | Must be in the language catalog. |
| `subtitle_enabled` | `false` | — |
| `subtitle_languages` | `null` | List of supported codes; deduped; auto-populated to `[video_language]` if `subtitle_enabled=true` and the list is empty. |
| `subtitle_format` | `"srt"` | `"srt"` or `"vtt"`. |
| `subtitle_burn_in` | `false` | Persisted but **not implemented** — captions remain sidecar files. |
| `transcript_language` | `null` | Optional override for future forced alignment. |

## Subtitle artifacts

When `subtitle_enabled=true` and `script_text` is non-empty, the
`POST /api/v1/jobs/from-inputs` handler writes one subtitle file per
requested language under
`/storage/artifacts/subtitles/<job_id>/<lang>.<ext>` and registers it as
`ArtifactType.subtitle`.

- **Mime:** `application/x-subrip` (SRT) or `text/vtt` (VTT).
- **Timing:** evenly-spaced cues. Metadata records
  `alignment="approximate"`, `real_timing=false`. Real forced alignment
  is future work.
- **Burn-in:** `burn_in_requested` is captured but the wrapper code
  intentionally records `burn_in_status="not_implemented"`. A future
  phase can light up an ffmpeg-based burner without changing the API
  contract.
- **Content endpoint:** `/api/v1/artifacts/<id>/content` streams the
  text bytes with the right mime type. Subtitle artifacts are in the
  serve allow-list.

## Frontend architecture

### Language context

[`frontend/lib/i18n/LanguageContext.tsx`](../../frontend/lib/i18n/LanguageContext.tsx)
provides `LanguageProvider`, `useLanguage`, and `useT`. On mount it:

1. Reads `localStorage["aivideo:ui-language"]` for an instant first paint.
2. Fetches `/api/v1/settings/ui`; backend wins if different.
3. Sets `<html lang="..." dir="..." >` on every change.
4. PATCHes the backend whenever the operator flips the dropdown.

### Dictionaries

`frontend/lib/i18n/dictionary.en.ts` and `dictionary.ro.ts`. Both
implement the same `Dictionary` TS type, which is exhaustive — the
typecheck refuses a build if a key is missing on either side. The
`test_phase11a_ui_i18n_static.py` test asserts parity for safety.

To add a string:

```ts
// 1. Add the key + default English value to dictionary.en.ts:
common: {
  ...
  newKey: "Hello world",
}

// 2. Add the corresponding entry to types.ts → Dictionary
// 3. Add the Romanian translation in dictionary.ro.ts.
// 4. Use it in components: const t = useT(); t("common.newKey")
```

Missing keys fall back to English, then to the raw key path — never
crash. The `lookup()` helper in `LanguageContext.tsx` enforces this.

### Help corpus

The canonical English corpus is `frontend/lib/help/content.ts`. Romanian
overrides live in `frontend/lib/help/content.ro.ts` as a
`Record<slug, HelpArticleOverride>` (partial — only the fields you want
to translate). `getLocalizedCorpus(language)` merges the override on top
of the English article at render time. Missing overrides fall back to
English; this is the spec-required fallback.

To translate a help article into Romanian:

```ts
// frontend/lib/help/content.ro.ts
export const HELP_ARTICLES_RO = {
  ...,
  "my-new-slug": {
    title: "Titlu românesc",
    summary: "Sumar românesc.",
    body: [{ type: "p", text: "Paragraf românesc." }],
  },
};
```

## Adding a new language (e.g. `fr`)

1. **Backend** — add a `LanguageInfo(code="fr", …)` row to `LANGUAGES`
   in `backend/app/core/languages.py`. Done. The schemas validate
   against the new code, and the catalog endpoint advertises it.
2. **Frontend i18n** — extend `SUPPORTED_LANGUAGE_CODES` +
   `LANGUAGE_META` in `frontend/lib/i18n/types.ts`. Create
   `frontend/lib/i18n/dictionary.fr.ts` with the same keys as the
   English dictionary. Register it in `DICTIONARIES` inside
   `LanguageContext.tsx`.
3. **Frontend help** — create
   `frontend/lib/help/content.fr.ts` with the overrides. Wire it into
   `getLocalizedCorpus()` in `content.ro.ts` (or rename that file
   later). Anything you don't translate falls back to English.

## Limitations of Phase 11A

- **Burn-in subtitles** — the field is persisted on the job and
  reported as `not_implemented` on the subtitle artifact metadata. The
  final-export bundle should list sidecar artifacts; an ffmpeg-burn
  pipeline is future work.
- **Language-aware scriptwriter** — `video_language` is persisted but
  the template scriptwriter doesn't yet branch on it. Ollama / future
  LLM providers can read it from the job context. Tracked as a Phase
  11A follow-up.
- **Forced alignment** — subtitle timing is approximate (cues spread
  evenly across `target_duration_seconds`). Real alignment lives in a
  future WhisperX-style stage.
- **Per-user settings** — `operator_settings` is a singleton until
  auth lands. The schema is shaped to grow into a per-user row without
  another migration.

## Help maintenance rule

Every UI change that touches a label, a control, a new error code, or a
new help article **must** update the relevant dictionary entry **in
both languages** and the matching help article (or its Romanian
override). The Phase 11A test
`tests/integration/test_phase11a_ui_i18n_static.py::test_en_and_ro_dictionaries_have_same_keys`
catches dictionary drift; the Phase 10C contribution rule still applies
(`docs/runbooks/contribution-rules.md`).

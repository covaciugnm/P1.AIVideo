# 04 — Frontend routes / pages / UI inventory

Framework: Next.js App Router (`frontend/app`). Build tooling verified: `npm run lint` → **No ESLint warnings or errors**; `npx tsc --noEmit` → **clean**. Container serves `/characters` → HTTP 200.

## Routes / pages (evidence: `find app -name page.tsx`)
| Route | File | Purpose |
|---|---|---|
| `/` | app/page.tsx | redirect → /characters |
| `/characters` | app/characters/page.tsx | list (alphabetical) |
| `/characters/new` | app/characters/new/page.tsx | create + available-voices |
| `/characters/[id]` | app/characters/[id]/page.tsx | profile tabs: Profile/Images/Videos/Settings + lifecycle bar + clone |
| `/jobs` | app/jobs/page.tsx | video list |
| `/jobs/new` | app/jobs/new/page.tsx | create video (CreateJobForm) |
| `/jobs/[jobId]` | app/jobs/[jobId]/page.tsx | job detail |
| `/jobs/[jobId]/edit` | app/jobs/[jobId]/edit/page.tsx | job edit |
| `/uploads` | app/uploads/page.tsx | uploads |
| `/settings` | app/settings/page.tsx | settings |
| `/technical-help` | app/technical-help/page.tsx | technical/help |

Navigation (`LocalizedNav`): Characters → Videos → Uploads → Settings → Technical → Help (Dashboard + New-Job removed). Bilingual EN/RO via i18n dictionaries; `tsc` enforces the key union in `lib/i18n/types.ts`.

## Character image library UI (`components/CharacterImageLibrary.tsx`)
- Legacy generate form (provider + prompt).
- **IdentityGenPanel (IG-4):** "Generate initial face" + scene/outfit/location/season/mood/pose/framing fields + aspect/quality selects + "Generate variation" (disabled until both canonical refs exist).
- Gallery `ImageCard`: thumbnail, **role badge**, provider, identity score + drift warning, accept/reject/archive/delete, set-main-reference, set-full-body-reference.

## Wired API clients (evidence: `rg` of client fns in components/app)
WIRED: `generateInitialImage`, `generateConsistentImage`, `cloneCharacter`, `transitionCharacterStatus`, `listAvailableVoices`, `setCharacterImageStatus` (accept/reject/archive/set-main-reference/set-full-body-reference).
**NOT WIRED (defined in lib, no caller):** `uploadReferenceImage`, `moderateReferenceImage` → HIGH finding (gated-upload + moderation UI missing).

## States
Forms show busy/disabled, status text, and `var(--danger)` error lines (IdentityGenPanel: `generating`/`done`/error). Mobile: `layout.tsx` exports viewport device-width; `globals.css` has `@media (max-width:768px)` + `(max-width:420px)`.

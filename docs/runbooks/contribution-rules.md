# Contribution rules — P1.AIVideo

> **One-line summary:** if the operator can see it or call it, it must be
> documented and helped. PRs/commits that touch the surface without touching
> the docs are incomplete.

This runbook is the source of the **Help & documentation maintenance rule**.
It is referenced from `README.md`, enforced by Phase 10C tests, and applies to
every change — code, infra, schema, model, UI.

## The rule

Any change that adds, removes, or modifies a user-visible surface **must update**:

1. The **runbooks** under `docs/runbooks/` that describe the surface.
2. The **help content** in `frontend/lib/help/content.ts`.
3. The **typed API client** in `frontend/lib/api.ts` *if* a backend route was
   added/changed.

A PR is considered incomplete if any of those three are stale relative to the
code change.

## Checklist (per change type)

Match the change against one of these rows. If it spans more than one row, do
**all** of them.

| You changed… | Update these |
|---|---|
| **API endpoint** — added / removed / renamed | `docs/runbooks/api-surface.md`, `frontend/lib/api.ts` (typed wrapper), `tests/integration/test_phase10c_api_surface.py` (assertion list), help if user-visible |
| **API request / response schema** | `frontend/lib/types.ts` (matching TS type), the relevant help article(s) that reference the schema |
| **Provider** — added a new provider id, status, or readiness gate | `docs/runbooks/provider-registry.md`, `frontend/lib/help/content.ts` (`providers-catalog`, `providers-status`, and a provider-specific article if it's a heavy-runtime), `tests/integration/test_phase10c_help_coverage.py` (if the new provider should be required) |
| **Runtime** — new model, new dep, new docker profile | the runtime-specific runbook under `docs/runbooks/` (e.g. `sadtalker-runtime.md`), a help article in the `video` / `voice` / `providers` section, `Makefile` targets if applicable |
| **Error code** — new categorised `*_error_code` | `docs/runbooks/api-surface.md` cross-cutting, help article `error-codes`, the relevant troubleshooting article |
| **UI page / route** | `docs/runbooks/ui-api-parity.md` (Pages section), a help article in section `ui`, a `<HelpHint>` on the page's `<h1>` |
| **UI control / button / form section** | `docs/runbooks/ui-api-parity.md` (the table row for the parent page), a `<HelpHint>` next to the control if non-obvious |
| **Setting** — added a new operator-visible setting | the `page-settings` help article, the `SettingsPanel` UI label, `docs/runbooks/ui-api-parity.md` |
| **Compliance surface** — new attestation, new C2PA / watermark detail | `docs/runbooks/compliance.md` (if present) + the `compliance-*` help articles |
| **Docker / compose service / profile** | `docs/runbooks/dev-setup.md` (or new runtime runbook), the `infra-docker-profiles` help article, `Makefile` targets, `docs/runbooks/api-surface.md` if env vars cross the API boundary |
| **Test** — new strict-mode warning suppression, new skip gate | the relevant runbook (so the next operator knows why it's skipped) |

## What "documented" means in practice

A doc update qualifies when:

- The **change is named** in the runbook (route path, env var, error code, etc.).
- A **future reader could reach the same conclusion** without grepping the diff.
- The **help article**, if any, is reachable from the in-app overlay (a row in
  the section nav, with at least a summary and a kv / list block).
- The **typed API client** has a function with a JSDoc one-liner that names the
  HTTP method + path. No raw `fetch()` calls in pages or components.

## How Phase 10C enforces this

These tests live under `tests/integration/test_phase10c_*.py` and run with
`pytest -q`. They are intentionally lightweight (no browser, no model load):

- **`test_phase10c_api_surface.py`** — Every endpoint listed in
  `api-surface.md` must exist on the live app. Conversely, every route the app
  exposes (under `/api/v1/*`) must be claimed by the doc.
- **`test_phase10c_ui_api_parity.py`** — Reads `frontend/lib/api.ts` + the
  `app/` page tree + selected components. Asserts the parity matrix doesn't
  drift (page exists, expected typed client function exists, a HelpHint anchor
  exists on every major page).
- **`test_phase10c_help_coverage.py`** — Walks `frontend/lib/help/content.ts`
  and asserts every required section + required provider topic + required
  error code is present. Empty topics fail the test.

Running the trio:

```bash
.venv/bin/python -m pytest -q tests/integration/test_phase10c_api_surface.py
.venv/bin/python -m pytest -q tests/integration/test_phase10c_ui_api_parity.py
.venv/bin/python -m pytest -q tests/integration/test_phase10c_help_coverage.py
```

A failure in any of these is a strong signal that someone shipped code without
updating docs. The fix is to update the doc / help (almost never to slack the
test).

## How to add a help article (3-step recipe)

1. Open `frontend/lib/help/content.ts`. Add a new entry to `HELP_ARTICLES`:
   ```ts
   {
     slug: "my-new-feature",
     title: "My new feature",
     section: "providers",            // or whichever section fits
     summary: "One sentence the operator can scan.",
     keywords: ["my", "new", "feature", "synonym"],
     body: [
       { type: "p", text: "Paragraph." },
       { type: "h", level: 3, text: "Subhead" },
       { type: "kv", rows: [["key", "value"]] },
       { type: "code", lang: "bash", text: "command here", caption: "what it does" },
       { type: "callout", tone: "warn", title: "Beware", text: "…" },
       { type: "linkArticle", slug: "related-article" },
     ],
     related: ["related-article"],
   }
   ```
2. Anchor it from the UI: add `<HelpHint slug="my-new-feature" />` next to the
   form section or button that the article describes. Or extend `related: []`
   on a sibling article so users can find it laterally.
3. Run the help-coverage test:
   ```bash
   pytest -q tests/integration/test_phase10c_help_coverage.py
   ```

## How to add an API endpoint (5-step recipe)

1. Implement the FastAPI route under `backend/app/api/<module>.py` with a typed
   request/response Pydantic schema (`ConfigDict(extra="forbid")`).
2. Register the router in `backend/app/main.py` if it's new.
3. Add a typed wrapper in `frontend/lib/api.ts` (one function per endpoint, no
   raw `fetch()` from components). Mirror the schema in `frontend/lib/types.ts`.
4. Add a row in `docs/runbooks/api-surface.md` under the matching group.
5. Update `frontend/lib/help/content.ts` — at minimum extend `error-codes` /
   `api-reference` / the relevant page topic. Add a `<HelpHint>` if a new UI
   button consumes the endpoint.

## Pointer to the live test suite

`tests/integration/test_phase10c_help_coverage.py` is the canonical place to
**add a new "required topic"** when you add a new feature class. The list there
is the only knob — touch nothing else.

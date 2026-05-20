# Public / private layout + auth UI separation — report

## 1. Files changed
- `frontend/components/AppFrame.tsx` (NEW) — single decider: public routes render page-only (no shell); protected routes render the internal shell ONLY after a token is confirmed, else Splash + redirect to /login.
- `frontend/app/layout.tsx` — root layout no longer renders the shell globally; delegates to `<AppFrame>`. Added favicon/icon metadata (AIVideo1.png) + title/description.
- `frontend/app/page.tsx` — was a redirect to /characters; now the PUBLIC landing page (logo + RO/EN description + Login/Register).
- `frontend/app/login/page.tsx` — logo + RO status messages (pending/suspended/rejected) + Home link, public styling.
- `frontend/app/register/page.tsx` — logo + RO success message + Home link, public styling.
- `frontend/app/globals.css` — public palette (CSS vars) + `.public-landing/.public-card/.public-form/.auth-splash` styles.
- `frontend/public/AIVideo.png`, `frontend/public/AIVideo1.png` (copied from repo root).

## 2. Where logos were found
Repo root: `./AIVideo.png` (1254×1254) and `./AIVideo1.png` (344×246).

## 3. Where logos were copied/referenced
Copied to `frontend/public/AIVideo.png` and `frontend/public/AIVideo1.png` (no rename). Referenced as `/AIVideo.png` (landing/login/register large) and `/AIVideo1.png` (favicon + shell header small + auth splash).

## 4. Color palette used from logo
Extracted (Pillow) from AIVideo.png — dominant blues:
- `--aiv-primary: #0050e0` (bright blue)
- `--aiv-secondary: #0030d0` (deep blue)
- `--aiv-accent: #00c8f0` (cyan)
- `--aiv-bg: #0b1622` (dark navy) / `--aiv-panel: #14233a`
- `--aiv-text: #e8f1fb`
Used on public landing/login/register backgrounds, buttons, card borders, links, focus.

## 5. Public routes (no shell): `/`, `/login`, `/register`.
## 6. Protected routes (shell, auth required): `/characters`, `/characters/*`, `/jobs`, `/jobs/*`, `/uploads`, `/settings`, `/technical-help`, `/users`.

## 7. Auth guard implementation
`AppFrame` (client) computes `isPublicPath(pathname)`. Public → `<main>` only. Protected → `useEffect` reads `getToken()`; no token → `authState="noauth"` + `router.replace("/login")`; token present → `authState="authed"`. Until authed, renders a centered `Splash` (AIVideo1.png + "Checking access…"/"Redirecting…") — the internal shell is never rendered before auth is confirmed. `lib/api.ts` + `lib/characters.ts` attach the bearer token and, on HTTP 401, clear the session and redirect to /login (covers expired/invalid tokens and inactive users — backend returns 401 for those).

## 8. Internal shell not visible before login
Confirmed: the shell markup (header/nav/right sidebar/footer/help) lives ONLY inside `AppFrame`'s `authState === "authed"` branch. The static prerender of protected pages renders the Splash, not the shell. Public pages import none of the shell components.

## 9. /users visible only for protected super admin
`LocalizedNav` shows the Users link only when `isProtectedSuperAdmin(currentUser)` (is_protected && super_admin && active). The `/users` page itself re-checks and shows "Access denied" otherwise; the backend `/api/v1/users/*` is super-admin-gated regardless.

## 10. Build/lint/typecheck
`npx tsc --noEmit` clean · `npm run lint` clean (`--max-warnings 0`) · `npm run build` OK (15 static pages incl. /, /login, /register).

## 11. Runtime verification (live, :3010)
- `/` → 200, serves AIVideo.png, **0 `nav-links`** in HTML (no internal nav).
- `/login` → 200, `/register` → 200 (favicon AIVideo1.png referenced).
- `/characters` → 200 but initial HTML has **0 `nav-links`** and **1 `auth-splash`** → internal shell NOT rendered before auth.
- `/jobs` → 200 (same client-gated behavior).
- `GET /AIVideo.png` → 200 image/png · `GET /AIVideo1.png` → 200 image/png.
- Backend + UI static suite: **943 passed, 12 skipped** (two layout-marker tests updated to read AppFrame.tsx after the shell refactor).

## 12. Manual checks
Landing/login/register show the logo + no internal nav/sidebar/right bar; protected route without token → redirect to /login; login as P1.AIVideo-admin → shell appears + Users link visible; logout → back to /login, shell gone.

## 13. Remaining limitations
- Client-side guard: protected page HTML is served (200) then JS redirects — no SSR/middleware redirect (acceptable per spec "redirect OR client-side guard"; could add `middleware.ts` for a hard server redirect later).
- Token in localStorage (XSS exposure) — dev-phase choice.
- No frontend unit tests (Vitest) yet.
- Brief Splash flash possible before the client effect runs (no protected data leaks during it).

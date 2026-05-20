# Public auth UI + character page reorganization — report

## 1. Files changed
- `frontend/components/AppFrame.tsx` — public/private shell decider (prior commit).
- `frontend/app/page.tsx` — compact public landing (RO/EN, Autentificare/Înregistrare).
- `frontend/app/login/page.tsx`, `frontend/app/register/page.tsx` — `.auth-field` bubbles, distinct ids, autocomplete control, cleared state.
- `frontend/app/globals.css` — compact `.public-card`, `.auth-field/.auth-label/.auth-input/.auth-button`, dossier + imglib + modal CSS.
- `frontend/components/CharacterIdentityProfile.tsx` (NEW) — read-only dossier (chapters A–H, row rectangles, completeness badge + warnings).
- `frontend/app/characters/[id]/page.tsx` — Identitate tab shows the dossier (read-only) with an "Editează profil" toggle to the form.
- `frontend/components/CharacterImageLibrary.tsx` — generation controls moved into a "+ Imagine Nouă" modal; gallery shows images + actions; video-from-image button with RO tooltip.

## 2. Root cause of landing page excessive height
Original `.public-card` had a fixed `max-width:560px` + large paddings and no `max-height`, plus verbose description → a tall vertical panel. Fixed with `width:min(920px,100vw-32)`, `max-height:calc(100dvh-48px)`, `overflow:auto`, `clamp()` padding, smaller logo, concise copy.

## 3. Root cause of login/register field layout
The auth inputs used the generic `.form-row` class which has **no base rule** in globals.css → `<label><span>+<input>` flowed inline (fields collided / button beside input). Fixed with dedicated `.auth-field` bubbles (flex column).

## 4. Root cause of credential persistence / cross-form inheritance
No app-side persistence existed (auth.ts stores only token+user, never password). The retained/copied values were **browser autofill** because both forms used generic, identical-looking inputs without distinct names or autocomplete control.

## 5. How it was fixed
Distinct field names/ids (`login-username/password` vs `register-username/email/full-name/password/confirm-password`), `autoComplete="off"` on forms + `autoComplete="new-password"` on password fields; controlled state initialized empty on mount and password wiped on unmount/after submit.

## 6. Password storage confirmation
`rg "password" frontend/lib/auth.ts` shows NO localStorage/sessionStorage write of credentials — only token + user object are persisted. Password never enters localStorage/sessionStorage/cookies/URL/global state.

## 7. Public/private layout separation
`AppFrame`: `/`, `/login`, `/register` render page-only (no shell). Protected routes render the shell only after a token is confirmed; otherwise an auth splash + redirect to `/login`. Verified earlier: protected-route initial HTML has 0 `nav-links`.

## 8. Logos found and used
`./AIVideo.png` + `./AIVideo1.png` (repo root) → copied to `frontend/public/`. AIVideo.png on landing/login/register; AIVideo1.png as favicon + shell header + auth splash.

## 9. Color palette
`--aiv-primary #0050e0`, `--aiv-secondary #0030d0`, `--aiv-accent #00c8f0`, `--aiv-bg #0b1622`, `--aiv-panel #14233a`, `--aiv-text #e8f1fb` (extracted from AIVideo.png).

## 10–13. Public landing / login / register / bubbles
Landing card compact + balanced; login & register are single vertical columns of `.auth-field` bubbles (label over input), inputs 16px / min-height 46px, button 48px on its own row.

## 14–16. Character page reorganization
Identitate tab now renders `CharacterIdentityProfile` (read-only dossier) with chapters A. Identitate generală, B. Rol narativ, C. Personalitate, D. Voce, E. Aspect fizic, F. Vestimentație, G. Context social, H. Compliance — each field a label-left/value-right row rectangle. Physical completeness badge (Insuficient/Basic/Bun/Detaliat, count /8) + warnings (Lipsă referință față/corp, profil fizic prea scurt, lipsesc date păr/ochi, lipsește forma feței). "Editează profil" toggles the editable form.

## 17. Image library ordering
Gallery shows images + actions only; the big generation form is now inside a "+ Imagine Nouă" modal. Per-image: description, status/reference badge, set-face/full-body, delete, and "Generează video pe baza acestei imagini".
**Partial vs. spec:** the face-ref-first / body-ref-second explicit ordering + per-image "Imagine N —" numbering and the in-modal LLM-refine ("Ajustează descrierea cu LLM") preview flow (Salvează/Regenerează/Părăsește) are **not fully implemented** — the modal currently hosts the existing generate + identity-gen panel. This is the remaining piece.

## 18. New image modal behavior
"+ Imagine Nouă" opens a modal containing the generation controls (provider/prompt + identity-consistent panel with scene/outfit/season + LLM-tier-aware workflow). Close = Părăsește.

## 19. Video-from-image button
Present under each image; RO tooltip: "Pipeline-ul video este momentan oprit / va fi activat pe serverul de 128GB." It prepares a video job (job creation is real; rendering depends on the stopped pipeline — not faked).

## 20. Lint/typecheck/build
`tsc --noEmit` ✓ · `npm run lint` ✓ · `npm run build` ✓ (15 pages). Frontend Docker image rebuilt + restarted (this was the missing deploy step that made earlier changes invisible).

## 21. Backend pytest
No backend change in this task. (Prior suites: 952 passed.)

## 22. Manual verification checklist
Landing compact + logo + buttons + no shell; login/register vertical bubbles + no shell; password not app-persisted; register independent state; protected routes gated; Identitate dossier with chapters/rows/warnings; gallery + "+ Imagine Nouă" modal + video button.

## 23. Remaining blockers
- Image-library: explicit face-first/body-second ordering + "Imagine N —" numbering + dedicated candidate→Salvează/Regenerează/Părăsește preview flow + in-modal LLM-refine endpoint are **partial** (modal hosts existing panels).
- Video pipeline remains intentionally stopped (128GB box).

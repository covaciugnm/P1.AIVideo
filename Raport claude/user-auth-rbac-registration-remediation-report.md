# User authentication / registration / approval / RBAC — remediation report

Security remediation for: backend had NO authentication; `/api/v1/secrets/*`
and `/api/v1/system/logs/backend` were world-readable. Now fixed with a real
user system + JWT + RBAC + protected super admin.

## 1. Branch
`security/user-auth-rbac-registration` (off `feature/identity-image-pipeline-audit-stabilized`).

## 2. Files changed (key)
**Backend:** `models/user.py` (new), `models/__init__.py`, `alembic/versions/0011_users_auth.py` (new), `services/auth_service.py` (new), `services/user_service.py` (new), `core/security.py` (new), `core/config.py` (P1_* settings + assert_auth_config; removed `phase2-noop-changeme`), `api/auth.py` (new), `api/users.py` (new), `api/system.py` (logs guarded), `api/jobs.py` (create gated), `main.py` (bootstrap + router protection), `schemas/auth.py` (new), `pyproject.toml` (argon2-cffi, PyJWT).
**Frontend:** `lib/auth.ts` (new), `lib/users.ts` (new), `lib/api.ts` + `lib/characters.ts` (token attach + 401 redirect), `app/login/page.tsx` (new), `app/register/page.tsx` (new), `app/users/page.tsx` (new), `components/LocalizedNav.tsx` (auth gate + username/logout + Users link).
**Config/tests:** `.env` (P1_* real values — gitignored), `.env.example` (placeholders), `tests/conftest.py` (auth off for legacy suite), `tests/integration/test_phase_auth_rbac.py` (new, 17 tests), `tests/integration/test_phase10c_api_surface.py` (auth routes documented).

## 3. Migration revision id
`0011_users_auth` (revises `0010_ig3_image_meta`). Applied to live DB; head = `0011_users_auth`.

## 4. User model fields
id, username(unique), email(unique, nullable), full_name, password_hash (never exposed), role, user_status, is_active, is_protected, created_at, updated_at, last_login_at, password_changed_at, approved_at/by, rejected_at/by/reason, suspended_at/by/reason, deleted_at/by/reason. Indexes: username(uniq), email(uniq), role, user_status, is_active, is_protected.

## 5. Auth endpoints
`POST /api/v1/auth/register` (public, pending/operator/inactive, no token) · `POST /api/v1/auth/login` (public, JWT) · `GET /api/v1/auth/me` · `POST /api/v1/auth/change-password` · `POST /api/v1/auth/logout` (client-side discard).

## 6. Registration flow implemented: YES (public → pending; never auto-login; privileged fields ignored).
## 7. Approval flow implemented: YES (super-admin approve → active+role).
## 8. User status management implemented: YES (approve/reject/suspend/reactivate/soft-delete with transition validation).

## 9. Protected super admin behavior
Username `P1.AIVideo-admin`, role super_admin, active, is_protected. Bootstrapped at startup from `P1_SUPER_ADMIN_PASSWORD` (env only, never logged/exposed). Re-bootstrap repairs role/status/flags WITHOUT touching the password. Cannot be deleted/suspended/rejected/demoted/renamed/un-protected via API (guard in `user_service._guard_not_protected`; verified 403). Only itself can change its password (current password required).

## 10. Public routes
`GET /healthz`, `POST /api/v1/auth/login`, `POST /api/v1/auth/register`, plus low-risk `GET /api/v1/system/status` + `/config/*` (shell metadata).

## 11. Protected routes
All other `/api/v1/*` require a valid bearer token (active user). Super-admin-only: `/api/v1/secrets/*`, `/api/v1/system/logs/backend`, `/api/v1/users/*`. Operator+ (write): `POST /api/v1/jobs`.

## 12. RBAC policy table
| Resource | unauth | viewer | operator | admin | super_admin |
|---|---|---|---|---|---|
| /secrets/* | 401 | 403 | 403 | 403 | 200 |
| /system/logs/backend | 401 | 403 | 403 | 403 | 200 |
| /users/* | 401 | 403 | 403 | 403 | 200 |
| POST /jobs | 401 | 403 | ✓ | ✓ | ✓ |
| product reads (characters/jobs lists, providers…) | 401 | ✓ | ✓ | ✓ | ✓ |

(Admin is intentionally denied secrets/logs/users this phase, per spec.)

## 13. Shared workspace data policy
**Per-user data isolation is NOT implemented in this phase. All approved users operate on shared workspace data** (same characters/jobs/uploads/images/videos/settings). Surfaced on the /users page.

## 14. Curl verification proof (live, :8001)
```
healthz 200 · UNAUTH /secrets 401 · UNAUTH /system/logs/backend 401
register test-operator 200 (pending) · login-before-approval 403
admin login → token (len 277) · /auth/me 200 · super-admin /secrets 200 · /logs 200
approve operator 200 · approved login 200
operator /users/pending 403 · operator /secrets 403
suspend 200 · suspended login 403 · reactivate 200 · soft-delete 200 · deleted login 403
DELETE protected super admin 403
```

## 15. Test results
Backend: **943 passed, 12 skipped** (`pytest tests/ -q`) — includes 17 new auth/RBAC tests; legacy 926 run with `P1_AUTH_ENABLED=false`. Storage test root overridden to tmp via conftest.

## 16. Frontend verification
`npx tsc --noEmit` clean · `npm run lint` clean · `npm run build` OK (/login, /register, /users compiled). Token attached to all API calls; 401 → clear session + redirect /login; Users nav shown only to protected super admin. No frontend unit-test runner exists (only typecheck) — see remaining risks.

## 17. Remaining security risks
- No email verification. No password reset by email. No brute-force/rate limiting. No refresh-token rotation. No token blacklist (logout is client-side discard). No per-user data isolation. No durable DB audit log for admin actions (events go to logs). Token stored in localStorage (XSS exposure) — dev-phase choice. `admin` role currently has no elevated user-management powers (super-admin-only by design this phase). No frontend unit tests yet.

## 18. Recommended next hardening
Refresh tokens + revocation/blacklist; rate limiting + brute-force protection; Cloudflare Access JWT validation at the edge; CSRF strategy if moving to cookies; persistent audit log for admin/security actions; per-user ownership for jobs/characters/uploads; httpOnly cookie storage; Vitest component tests for login/register/users.

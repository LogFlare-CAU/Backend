# Code health — 2026-07-15 (backend-api)

| Field | Value |
|-------|--------|
| Date | 2026-07-15 |
| Scope | Full backend (`app/`, compose, CI, README); org [LogFlare-CAU/Backend](https://github.com/LogFlare-CAU/Backend) |
| Auditor | Cursor agent |
| Repo | LogFlare / LogFlare-CAU/Backend |

## Executive summary

Study-era FastAPI backend with a solid response envelope and feature-module split, but weak auth lifetime/revocation, traceback leakage, SQLite+destructive `init_db`, and no tests. Phase 1–3 remediations from this audit were implemented in Agent mode on 2026-07-15.

## Findings

### Dead code

| ID | Path | Symbol / lines | Confidence | Notes |
|----|------|----------------|------------|-------|
| CH-2026-07-15-17 | `user/authenticate.py` | `_crosscheck_token` | high | Replaced by login-path DB cross-check |

### Security & vulnerabilities

| ID | Severity | Area | Summary | Evidence (no secrets) |
|----|----------|------|---------|------------------------|
| CH-2026-07-15-01 | Critical | errors | 500 returns full traceback | `main.py` generic handler |
| CH-2026-07-15-02 | Critical | project auth | Project JWT not bound/revocable via DB | `projects/service.py`, `authenticate.py` |
| CH-2026-07-15-03 | Critical | user auth | DB token store unused | `_crosscheck_token` no-op |
| CH-2026-07-15-04 | High | user auth | Missing/`-1` expire_at never expires | authenticate + `create_token` |
| CH-2026-07-15-05 | High | authz | perm from JWT claim only | `_require_moderator` |
| CH-2026-07-15-06 | High | authz | Moderator can set ADMINISTRATOR | `UserCreateParams` |
| CH-2026-07-15-07 | High | FCM | Full google-services JSON to any login | `GET /fcm/data` |
| CH-2026-07-15-08 | High | ops | Superuser password logged plaintext | `user/init.py` |
| CH-2026-07-15-09 | High | LFI | Absolute logfile paths opened as-is | `logs/application.py` |
| CH-2026-07-15-10 | High | crypto | Shared JWT secret for user+project | `jwt_utils.py` |

### Maintainability & other

| ID | Type | Path | Summary |
|----|------|------|---------|
| CH-2026-07-15-11 | migrations | `init_db.py`, `.gitignore` | Migrations wiped / gitignored |
| CH-2026-07-15-12 | bug | `user/model.py` vs `service.py` | `updated_at` used but missing on model |
| CH-2026-07-15-13 | bug | `logs/service.py`, `application.py` | Sort override; Python-side ACL filter |
| CH-2026-07-15-14 | session | `logs/router.py`, `tasks.py` | BackgroundTasks reuse request session |
| CH-2026-07-15-15 | docs/ops | README, env templates | Run path / docs / env key mismatch |
| CH-2026-07-15-16 | test-gap | repo | No tests; OpenAPI-only CI; unpinned deps |
| CH-2026-07-15-18 | low | schemas | Default password `"password"`; no login rate limit |

## Planned actions

| ID | Priority | Action | Effort | Risk | Owner / status |
|----|----------|--------|--------|------|----------------|
| CH-2026-07-15-01..16 | — | See remediation log | — | — | done (2026-07-15) |
| CH-2026-07-15-18 | 4 | Login rate limit | M | low | deferred |

## Open questions

- DB remains SQLite with env-overridable DSN (Postgres later).
- Compose personal volumes moved to `compose.override.example.yaml` / gitignored override.

## Remediation log

| Date | ID | Status | Summary of change |
|------|-----|--------|-------------------|
| 2026-07-15 | CH-2026-07-15-01 | done | 500/409 hide internals; log server-side; validation errors JSON-safe |
| 2026-07-15 | CH-2026-07-15-04 | done | Standard JWT `exp` + `jti`; session 15m / keep-logged 30d |
| 2026-07-15 | CH-2026-07-15-03 | done | Login cross-checks DB token row (revocation) |
| 2026-07-15 | CH-2026-07-15-02 | done | Opaque project keys; DB equality; `POST .../rotate-token` |
| 2026-07-15 | CH-2026-07-15-10 | done | Project keys no longer use JWT/`JWT_SECRET` |
| 2026-07-15 | CH-2026-07-15-05 | done | Moderator check uses DB `User.permission` |
| 2026-07-15 | CH-2026-07-15-06 | done | Schema validators block assigning ADMINISTRATOR |
| 2026-07-15 | CH-2026-07-15-07 | done | `/fcm/data` returns minimal client fields |
| 2026-07-15 | CH-2026-07-15-08 | done | Superuser create log omits password |
| 2026-07-15 | CH-2026-07-15-09 | done | `LOGFLARE_LOG_ROOTS` allowlist via `path_utils` |
| 2026-07-15 | CH-2026-07-15-11 | done | `init_db` keeps migrations; `.gitignore` no longer ignores them |
| 2026-07-15 | CH-2026-07-15-12 | done | `users.updated_at` column + alembic revision |
| 2026-07-15 | CH-2026-07-15-13 | done | SQL `IN (project_ids)` + fixed sort |
| 2026-07-15 | CH-2026-07-15-14 | done | `notify_error` opens fresh session by `error_id` |
| 2026-07-15 | CH-2026-07-15-15 | done | README/CLAUDE/env template/compose hygiene |
| 2026-07-15 | CH-2026-07-15-16 | done | pytest smoke + ruff CI workflow; pinned `requirements.txt` |
| 2026-07-15 | CH-2026-07-15-17 | done | Stub removed / auth path cleaned |
| 2026-07-15 | CH-2026-07-15-18 | deferred | Login rate limiting left for later |

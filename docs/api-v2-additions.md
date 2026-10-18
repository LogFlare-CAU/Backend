# API additions (app rework)

Reference for the endpoints and ingest fields added in the app rework. All responses use the standard envelope `{ success, message, error_code, data }`. Auth is either a user JWT (`Authorization: Bearer <jwt>`) or, for ingest, the project headers (`Project` + `ProjectKey: Bearer <key>`).

## Deploy

Run the migration before starting the new server (migration `b7c1d2e3f4a5`, revises `b7c8d9e0f1a2` (error_groups); adds `errorlogs.logfile_id`, `errorlogs.raw`, two indexes, and uppercases existing `level` values). On SQLite the `errorlogs` table is rebuilt (batch mode): it holds the write lock for the whole run, needs about 2x the table size in free disk, and takes roughly 10-15 s per million rows. Production must already be at `b7c8d9e0f1a2`.

Procedure (Docker host, repo root):

1. **Stop** the server (this also stops the collector): `docker compose stop logflare`.
2. **Back up** `app/db/mydb.sqlite` together with any `mydb.sqlite-journal` / `-wal` / `-shm` next to it (e.g. `cp -p app/db/mydb.sqlite* /backup/logflare-$(date +%F)/`).
3. **Check out** the new code (`git pull` / checkout of the release commit).
4. **Migrate**: `docker compose run --rm --no-deps -w /app/alembic logflare alembic upgrade head`. Alembic must run from `app/alembic` (`/app/alembic` in the container): `alembic.ini` resolves the DB as `../db/mydb.sqlite` relative to that directory.
5. **Verify** (same `docker compose run --rm --no-deps -w /app/alembic logflare ...` prefix, or `sqlite3 app/db/mydb.sqlite` on the host):
   * `alembic current` shows `b7c1d2e3f4a5 (head)`;
   * `SELECT COUNT(*) FROM errorlogs` equals the pre-migration count;
   * `PRAGMA foreign_key_list(errorlogs)` lists `projects` (CASCADE) and `log_files.logfile_id` (SET NULL);
   * `PRAGMA integrity_check` returns `ok`;
   * `SELECT COUNT(*) FROM errorlogs WHERE level != UPPER(level)` returns 0.
6. **Start**: `docker compose up -d logflare`.
7. **Smoke test**: `GET /log/` (health), log in, `GET /log/summary`, `GET /log/events?limit=5`, open one `GET /log/events/{id}`, and `POST /log/error` with `"test": true` (204).

If verification fails, stop the server and restore the backup files.

## New endpoints

### Logs

| Method + path | Auth | Parameters | Response `data` |
|---|---|---|---|
| `GET /log/summary` | login | `project_id` (optional, 403 if no access), `hours` (1-168, default 24) | `window_hours`, `since`, `counts` (level to count), `projects[]` (`project_id`, `error_count`, `warning_count`, `last_error_at`) |
| `GET /log/events` | login | `project_id`, `min_level` (DEBUG, INFO, WARNING, ERROR, CRITICAL), `logfile_id`, `since`, `until`, `q` (case-insensitive match on message/errortype), `sort` (newest, oldest, highest, lowest; default newest), `grouped` (default true), `limit` (1-200, default 50), `cursor` | `items[]` (`id`, `project_id`, `logfile_id`, `logfile_name`, `errortype`, `message`, `level`, `timestamp`, `occurrences`, `first_seen`, `last_seen`, `group_key`), `next_cursor`. Bad cursor returns 400. |
| `GET /log/events/{error_id}` | login | path `error_id` | Event fields above, plus `occurred_at`, `row_level`, `raw` and `recent_ids` (up to 10 newest IDs in the same group, excluding this one). 403 without project access, 404 if missing. |

#### Semantics

* `hours` (summary) is clamped to 1..168.
* `since` / `until` accept ISO 8601 with or without a UTC offset; offsets are converted to UTC (`11:00+09:00` is `02:00Z`). Values without an offset are treated as UTC.
* `cursor` is opaque and only valid with the same filters and sort that produced it. A malformed cursor returns 400.
* Pagination caveat: the cursor is an offset plus a time ceiling fixed at the first page (rows newer than the first page are excluded, so new errors do not shift pages). The docker log collector can insert rows with **past** timestamps (backfill after a restart or a slow poll); such rows fall under the ceiling and can shift offsets, so a later page may repeat or skip an item. Pull-to-refresh (dropping the cursor) resolves it; clients should de-duplicate by `id`/`group_key` when appending pages.
* `q` is a literal, case-insensitive substring match (`%` and `_` have no special meaning).
* Response timestamps (`since`, `last_error_at`, `timestamp`, `first_seen`, `last_seen`, `occurred_at`) are ISO 8601 in UTC with an explicit offset, e.g. `2026-10-18T03:00:00.123456+00:00` (same format as `/group` and `/summary`; fractional seconds appear when stored).

**Grouping (list).** With `grouped=true` (default), events are grouped by the error group fingerprint that ingest computes (`errorlogs.fingerprint`, the same key as `/group`): normalized message (numbers, ids, quoted strings, timestamps masked) plus source and level, scoped to the project. So `user 12 not found` and `user 34 not found` are one group. Rows without a fingerprint fall back to (project, errortype, message; NULL errortype is its own group); the migration backfills fingerprints, so this only affects rows written outside the normal ingest path. Groups marked `ignored` via `PATCH /group/{id}` are **not** filtered out (the app has no ignore UI). The item's `errortype` and `message` are those of the latest row in the group. `group_key` (string) identifies the group exactly as the server grouped it: the `fingerprint` when the rows have one, otherwise the SHA-1 hex of `p:{project_id}|t:{errortype or ''}|m:{message}`. With `grouped=false` each row still carries its group's `group_key`, and the detail response carries it too. Old clients can ignore it. Per item: `id` is the latest row id in the group, `level` is the highest level in the group, `timestamp` equals `last_seen`, and `occurrences` counts the rows that match the active filters. With `grouped=false`, `id` is the row id and `occurrences` is 1.

**Detail.** `GET /log/events/{id}` returns row-specific fields from the requested row: `id`, `raw`, `occurred_at` (the row's timestamp), `row_level` (the row's level, uppercase), `logfile_id`, `logfile_name`. Group-wide fields cover the whole group: `occurrences`, `first_seen`, `last_seen`, `level` (highest) and `timestamp` (= `last_seen`, same as the list). Detail `occurrences` is all-time, whereas list counts respect the filters.

### Projects

| Method + path | Auth | Response `data` |
|---|---|---|
| `GET /project/{projectid}/token` | moderator (>= 80) with access to the project | Project record including its `token` (ProjectKey). 401 unauthenticated, 403 if not a moderator or the moderator has no access to the project (administrators see all), 404 if the project does not exist. |

### FCM

| Method + path | Auth | Body / response |
|---|---|---|
| `POST /fcm/token` | login | Body `{ "fcm_token": string }`. Returns the stored token record (`FCMTokenResponse`). Idempotent: registering the same token again refreshes it and reassigns it to the calling user if the device changed account. |
| `DELETE /fcm/token` | login | Body `{ "fcm_token": string }`. Removes only a token owned by the caller. The body is JSON, so Retrofit needs `@HTTP(method = "DELETE", path = "/fcm/token", hasBody = true)`. Returns `{ "removed": bool }`; `false` if the token belongs to someone else or does not exist. |

## Changed existing behavior

### `POST /log/error` (ingest)

Two new optional fields in the body, alongside `errortype`, `level`, `message`, `test`:

* `logfile` (string, optional): name of a log file registered to the project (`POST /project/{id}/logfile`). If no file with that name exists, `logfile_id` is stored as `NULL`.
* `raw` (string, optional): original log payload. Truncated to the first 65,536 characters, then secrets are masked the same way as `message` (`password=***`, `Bearer ***`, URL credentials; a secret cut at the boundary is masked too), and the result is capped at 65,536 characters again.

Both are optional, so existing clients keep working. The response is still `204`. Ingest still records the error group and sends the "new group" push as before.

### Level normalization

`level` is stored uppercased (`error` becomes `ERROR`). Filters and summaries also compare uppercased values, so existing lowercase rows from before the migration are handled as well.

### `GET /log/error`

Items no longer include `raw` (use `GET /log/events/{id}`) or the `project` / `logfile` relation keys. Before the rework every item carried `"project": null` (the response DTO declared the relation but it was never filled); that key is now dropped. This is a non-breaking removal, since its value was always `null`. Keys are `id`, `project_id`, `errortype`, `message`, `level`, `timestamp`, `logfile_id`, `fingerprint` (`fingerprint` was already returned by this server before the app rework). Timestamps here keep the existing format without an offset (UTC).

### `GET /log/{project_id}/{logfileid}`

Unchanged. Still reads a registered log file.

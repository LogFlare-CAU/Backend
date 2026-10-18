# API additions (app rework)

Reference for the endpoints and ingest fields added in the app rework. All responses use the standard envelope `{ success, message, error_code, data }`. Auth is either a user JWT (`Authorization: Bearer <jwt>`) or, for ingest, the project headers (`Project` + `ProjectKey: Bearer <key>`).

## Deploy

Run the migration before starting the new server (migration `b7c1d2e3f4a5`, adds `errorlogs.logfile_id`, `errorlogs.raw`, two indexes, and uppercases existing `level` values):

```bash
cd app/alembic && alembic upgrade head
```

## New endpoints

### Logs

| Method + path | Auth | Parameters | Response `data` |
|---|---|---|---|
| `GET /log/summary` | login | `project_id` (optional, 403 if no access), `hours` (1-168, default 24) | `window_hours`, `since`, `counts` (level to count), `projects[]` (`project_id`, `error_count`, `warning_count`, `last_error_at`) |
| `GET /log/events` | login | `project_id`, `min_level` (DEBUG, INFO, WARNING, ERROR, CRITICAL), `logfile_id`, `since`, `until`, `q` (case-insensitive match on message/errortype), `sort` (newest, oldest, highest, lowest; default newest), `grouped` (default true), `limit` (1-200, default 50), `cursor` | `items[]` (`id`, `project_id`, `logfile_id`, `logfile_name`, `errortype`, `message`, `level`, `timestamp`, `occurrences`, `first_seen`, `last_seen`), `next_cursor`. Bad cursor returns 400. |
| `GET /log/events/{error_id}` | login | path `error_id` | Event fields above, plus `occurred_at`, `row_level`, `raw` and `recent_ids` (up to 10 newest IDs in the same group, excluding this one). 403 without project access, 404 if missing. |

#### Semantics

* `hours` (summary) is clamped to 1..168.
* `since` / `until` accept ISO 8601 with or without a UTC offset; offsets are converted to UTC (`11:00+09:00` is `02:00Z`). Values without an offset are treated as UTC.
* `cursor` is opaque and only valid with the same filters and sort that produced it. A malformed cursor returns 400.
* `q` is a literal, case-insensitive substring match (`%` and `_` have no special meaning).

**Grouping (list).** With `grouped=true` (default), events are grouped by (project, errortype, message; NULL errortype is its own group). Per item: `id` is the latest row id in the group, `level` is the highest level in the group, `timestamp` equals `last_seen`, and `occurrences` counts the rows that match the active filters. With `grouped=false`, `id` is the row id and `occurrences` is 1.

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
* `raw` (string, optional): original log payload. Stored truncated to the first 65,536 characters.

Both are optional, so existing clients keep working. The response is still `204`.

### Level normalization

`level` is stored uppercased (`error` becomes `ERROR`). Filters and summaries also compare uppercased values, so existing lowercase rows from before the migration are handled as well.

### `GET /log/error`

Items no longer include `raw` (use `GET /log/events/{id}`) or the `project` / `logfile` relation keys. Keys are `id`, `project_id`, `errortype`, `message`, `level`, `timestamp`, `logfile_id`.

### `GET /log/{project_id}/{logfileid}`

Unchanged. Still reads a registered log file.

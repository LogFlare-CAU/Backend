# LogFlare Backend Server

FastAPI backend that centralizes log/error ingestion for registered projects. Each project has an opaque API key (`ProjectKey`). Responses use a standard envelope; live Swagger UI is disabled (schema is published separately).

## Requirements

* Python 3.12+
* SQLite by default (`LOGFLARE_DATABASE_URL` overridable)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp logflare.env.copy logflare.env   # or export vars; Compose uses logflare.env
# Edit JWT_SECRET, SUPERUSER_*, FCM_*, LOGFLARE_LOG_ROOTS
```

## Database

```bash
python app/init_db.py
```

This **deletes only the SQLite DB file** and runs `alembic upgrade head`. Migration scripts under `app/alembic/migrations/` are kept and should be committed.

Alembic: run commands from `app/alembic/` (`script_location = migrations`).

## Run

Imports are rooted at `app/` (see `CLAUDE.md`). Prefer:

```bash
cd app
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# or: python main.py   # uses LOGFLARE_API_PORT
```

Docker Compose (optional, local ops):

```bash
# Optional machine-specific binds:
cp compose.override.example.yaml docker-compose.override.yaml
docker compose up -d --build
```

## Tests / lint

```bash
pytest
ruff check app tests scripts
```

## API notes

* Envelope: `{ success, message, error_code, data }`
* User auth: `Authorization: Bearer <jwt>` (finite TTL; DB-backed revocation)
* Project ingest: headers `Project` + `ProjectKey: Bearer <opaque-key>`
* Rotate project key: `POST /project/{id}/rotate-token` (moderator)
* Logfile paths must be under `LOGFLARE_LOG_ROOTS` (comma-separated)
* Interactive docs are off on the live app (`docs_url=None`). Published schema:
  [Swagger viewer](https://macqueen0987.github.io/swagger-viewer/?spec=https://raw.githubusercontent.com/LogFlare-CAU/Backend/openapi-jsons/openapi.json)

## CLI

```bash
cd app
python projectmanager.py
```

## Env template (`logflare.env.copy`)

| Variable | Purpose |
|----------|---------|
| `JWT_SECRET` | User JWT HMAC secret |
| `LOGFLARE_API_PORT` | Listen port when using `python main.py` |
| `LOGFLARE_API_ROOT_PATH` | FastAPI `root_path` (reverse proxy) |
| `LOGFLARE_DATABASE_URL` | Async SQLAlchemy URL |
| `LOGFLARE_LOG_ROOTS` | Allowed logfile directory roots |
| `SUPERUSER_NAME` / `SUPERUSER_PASSWORD` | Bootstrap admin |
| `FCM_KEY_FILE` / `FCM_GOOGLE_FILE` | Firebase credentials paths |

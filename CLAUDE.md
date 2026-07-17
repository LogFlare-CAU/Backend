# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

LogFlare is a FastAPI backend that centralizes log/error ingestion for other projects ("projects" are the registered log sources, each with their own JWT project key). It exposes a standardized JSON response envelope and auto-generated Swagger docs. Commit messages and comments in this repo are frequently in Korean.

## Commands

Run from repo root unless noted.

```bash
# install deps (Python 3.12+)
pip install -r requirements.txt

# one-time env setup
cp logflare.env.copy logflare.env    # then edit values (JWT_SECRET, SUPERUSER_*, FCM_*, LOGFLARE_LOG_ROOTS)

# create/reset the SQLite DB (deletes DB file only; keeps alembic migration scripts)
python app/init_db.py

# run the dev server (from app/, since imports are rooted at app/)
cd app
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# interactive CLI for managing projects/logfiles directly in the DB
cd app && python projectmanager.py

# export the OpenAPI schema to openapi.json (used by the external swagger-viewer)
python scripts/export_openapi.py app.main:app

# tests / lint
pytest
ruff check app tests scripts
```

### Database migrations (Alembic)

Alembic is rooted at `app/alembic` (`script_location = %(here)s/migrations`). Run alembic commands from `app/alembic/`. Commit files under `migrations/versions/`. `init_db.py` must not wipe migration scripts.

## Architecture

### Module layout: imports are rooted at `app/`

`app/main.py` is the entrypoint and is normally run as `uvicorn main:app` from inside `app/` — every internal import (`common.xxx`, `routes.xxx`) is relative to `app/`, not the repo root. Keep this in mind when adding scripts or running things from the repo root (see how `scripts/export_openapi.py` manually inserts both the repo root and `app/` onto `sys.path`).

### Feature module pattern (`app/routes/<feature>/`)

Each feature (`user`, `projects`, `logs`, `fcm`) is a self-contained package following the same file breakdown:

| File | Role |
|---|---|
| `model.py` | SQLAlchemy ORM declarations |
| `schema.py` | Pydantic DTOs (request/response) |
| `service.py` | Direct DB CRUD logic |
| `application.py` | Higher-level logic composed on top of `service.py` (cross-cutting/external-API concerns) |
| `router.py` | FastAPI `APIRouter` + endpoint declarations |
| `authenticate.py` | Feature-specific auth dependencies, where applicable (`user`, `projects`) |

New features should follow this same split rather than putting logic directly in `router.py`.

### Response envelope

Every endpoint response is expected to conform to `common.schema.APIResponse` (`success`, `message`, `error_code`, `data`) or a specialization of it. Do not return raw dicts/models from routers — wrap them:

```python
from common.schema import make_named_response, response_maker
from typing import Sequence
from .model import User

UserResponse = make_named_response(User, "UserResponse")               # single ORM object -> Swagger DTO
UserSequenceResponse = make_named_response(Sequence[User], "UserSequenceResponse")

@router.get("/", response_model=schema.UserResponse, responses=response_maker([404, 403]))
async def get_users(request: Request):
    ...
```

- `make_named_response` (`common/schema/sqlalchemy_orm_converter.py`) converts a SQLAlchemy ORM class into a Swagger-visible Pydantic DTO.
- `response_maker` (aliased `rm` in routers) auto-registers the common error responses (400/401/403/404/409/422/500) into a route's `responses=`.
- Global exception handlers in `app/main.py` translate `HTTPException`, `IntegrityError`, `RequestValidationError`, and any uncaught `Exception` into this same envelope — don't build ad-hoc error JSON in route handlers, just `raise HTTPException(...)`.
- Pre-built envelopes: `APIResponse`, `StringResponse`, `StringSequenceResponse`, `IntegerResponse`, `BooleanResponse`, `ErrorResponse` are all exported from `common.schema`.

### ORM serialization (`common/basemodel.py`)

All models inherit from `Base` (a `DeclarativeBase` subclass) which implements `__iter__`/`_to_dict` for manual dict conversion (used e.g. via `dict(log)` in `routes/logs/router.py`). Notes when adding fields to a model:
- Keys are auto-excluded if they match `__serialize_global_blacklist__` (token/password/secret/key-ish names) or contain `"token"` — sensitive columns are dropped from serialized output by default.
- Relationship traversal respects `__serialize_max_depth__` (default 1) and only serializes already-*loaded* relationships (checks `NO_VALUE`/expired state) — it will not trigger lazy loads.
- Per-model overrides: `__serialize_max_depth__`, `__serialize_include_manytoone_pk__`, `__serialize_exclude_keys__`, `__serialize_exclude_predicate__`.

### Auth model: two parallel schemes

There are two independent auth mechanisms:

1. **User auth** (`routes/user/authenticate.py`): `Authorization: Bearer <jwt>` (HS256, `JWT_SECRET`). Tokens use standard `exp` (+ `jti`), are stored in DB, and are cross-checked on every request (revocation). Moderator checks use **live** `User.permission` from DB, not the JWT `perm` claim. API create/update cannot assign `ADMINISTRATOR`. Use `get_userid(request)` (reads `request.state` set by the dependency).
2. **Project auth** (`routes/projects/authenticate.py`): opaque `ProjectKey` (not a JWT) must equal `Project.token` in DB; `Project` header must match the project name. Rotate with `POST /project/{id}/rotate-token`. Use `get_project_id(request)`.

Logfile paths are constrained by `LOGFLARE_LOG_ROOTS` (`common/path_utils.py`).

Pick the dependency that matches who's calling the endpoint — end users hit user-auth'd routes (`logs` read/query endpoints), while external services reporting logs/errors hit project-auth'd routes (`logs` write endpoints like `POST /log/error`).

### DB session

`common/sqlsession.py` uses `LOGFLARE_DATABASE_URL` (default `sqlite+aiosqlite:///db/mydb.sqlite`, relative to process CWD). SQLite enables `PRAGMA foreign_keys=ON`. Get a session via `conn=get_db` (already `Depends(...)`). Do **not** pass the request session into `BackgroundTasks` — open a fresh `async_session()` inside the task (see `routes/logs/tasks.py`).

### App startup (`app/main.py`)

- Routers for all four features are registered in one place; new features must be added to both the `from routes import ...` line and `app.include_router(...)`.
- `lifespan()` runs `fcm.init()` and `await user.init_superuser()` on startup — the latter seeds the superuser account from `SUPERUSER_NAME`/`SUPERUSER_PASSWORD` env vars.
- Swagger/OpenAPI is disabled on the live app (`docs_url=None, redoc_url=None, openapi_url=None`); the published Swagger docs are generated separately via `scripts/export_openapi.py` and hosted through an external swagger-viewer (see README).

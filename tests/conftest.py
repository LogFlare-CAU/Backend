"""Shared fixtures for the LogFlare API test suite."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURES.mkdir(exist_ok=True)
REPO_LOGS = ROOT / "logs"
REPO_LOGS.mkdir(exist_ok=True)

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

_TEST_DB = Path(__file__).resolve().parent / "_test.sqlite"
if _TEST_DB.exists():
    _TEST_DB.unlink()

os.environ["SUPPRESS_VARIABLE_NOT_ASSIGNED_ERROR"] = "true"
os.environ["JWT_SECRET"] = "test-jwt-secret-please-change-32b"
os.environ["LOGFLARE_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB.as_posix()}"
# Allow both the fixtures dir and the repo logs/ directory
os.environ["LOGFLARE_LOG_ROOTS"] = f"{FIXTURES.resolve()},{REPO_LOGS.resolve()}"
os.environ["SUPERUSER_NAME"] = "admin"
os.environ["SUPERUSER_PASSWORD"] = "adminpass1"
os.environ["LOGFLARE_API_PORT"] = "8000"
os.environ["FCM_KEY_FILE"] = ""
os.environ["FCM_GOOGLE_FILE"] = ""

os.chdir(APP_DIR)

from common.basemodel import Base  # noqa: E402
from common.enums import Permissions  # noqa: E402
from common.security import hash_password  # noqa: E402
from common.sqlsession import async_session, engine  # noqa: E402
from main import app  # noqa: E402
from routes.user import model as user_model  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    from common.rate_limit import _attempts as _login_rate_limit_attempts

    _login_rate_limit_attempts.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        session.add(
            user_model.User(
                username="admin",
                password=hash_password("adminpass1"),
                permission=Permissions.ADMINISTRATOR,
            )
        )
        await session.commit()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _login(client: AsyncClient, username: str, password: str, keep=False) -> str:
    res = await client.post(
        "/user/auth",
        json={
            "username": username,
            "password": password,
            "keep_logged_in": keep,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    return body["data"]


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient) -> str:
    return await _login(client, "admin", "adminpass1")


@pytest_asyncio.fixture
async def moderator(client: AsyncClient, admin_token: str):
    """Create a moderator account and return (username, password, token)."""
    res = await client.post(
        "/user/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "moduser",
            "password": "modpass12",
            "permission": Permissions.MODERATOR,
        },
    )
    assert res.status_code == 200, res.text
    token = await _login(client, "moduser", "modpass12")
    return "moduser", "modpass12", token


@pytest_asyncio.fixture
async def plain_user(client: AsyncClient, admin_token: str):
    """Create a normal user and return (username, password, token, user_idx)."""
    res = await client.post(
        "/user/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "normaluser",
            "password": "userpass1",
            "permission": Permissions.USER,
        },
    )
    assert res.status_code == 200, res.text
    idx = res.json()["data"]["idx"]
    token = await _login(client, "normaluser", "userpass1")
    return "normaluser", "userpass1", token, idx


@pytest_asyncio.fixture
async def project_with_key(client: AsyncClient, admin_token: str):
    res = await client.post(
        "/project/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "demo-project"},
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    return data["name"], data["token"], data["id"]


@pytest_asyncio.fixture
def sample_logfile(tmp_path_factory):
    """Writable log file under fixtures (allowed by LOGFLARE_LOG_ROOTS)."""
    path = FIXTURES / "sample.app.log"
    path.write_text(
        "2026-07-15 12:00:00 | INFO | hello\n"
        "2026-07-15 12:00:01 | ERROR | boom\n"
        "  stack line\n",
        encoding="utf-8",
    )
    return path

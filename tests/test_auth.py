"""User auth / authorization tests."""
import time

import jwt
import pytest
from httpx import AsyncClient

from common.enums import Permissions
from common.jwt_utils import decode_jwt
from routes.user.service import KEEP_LOGGED_TTL_SECONDS, SESSION_TTL_SECONDS


@pytest.mark.asyncio
async def test_login_and_me(client: AsyncClient, admin_token: str):
    res = await client.get(
        "/user/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["username"] == "admin"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    res = await client.post(
        "/user/auth",
        json={
            "username": "admin",
            "password": "wrongpass",
            "keep_logged_in": False,
        },
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_missing_auth_rejected(client: AsyncClient):
    res = await client.get("/user/me")
    assert res.status_code in (400, 401)


@pytest.mark.asyncio
async def test_garbage_token_rejected(client: AsyncClient):
    res = await client.get(
        "/user/me",
        headers={"Authorization": "Bearer not.a.jwt"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_session_token_has_short_exp(client: AsyncClient, admin_token: str):
    claims = decode_jwt(admin_token)
    assert "exp" in claims
    assert "jti" in claims
    assert claims["exp"] - claims["iat"] == SESSION_TTL_SECONDS


@pytest.mark.asyncio
async def test_keep_logged_in_has_longer_finite_exp(client: AsyncClient):
    res = await client.post(
        "/user/auth",
        json={
            "username": "admin",
            "password": "adminpass1",
            "keep_logged_in": True,
        },
    )
    assert res.status_code == 200
    claims = decode_jwt(res.json()["data"])
    assert claims["exp"] - claims["iat"] == KEEP_LOGGED_TTL_SECONDS
    assert claims["exp"] > int(time.time())


@pytest.mark.asyncio
async def test_expired_jwt_rejected(client: AsyncClient, admin_token: str, monkeypatch):
    # Forge an already-expired token with the same secret (still must fail decode).
    from common import jwt_utils

    expired = jwt.encode(
        {
            "idx": 1,
            "perm": Permissions.ADMINISTRATOR,
            "iat": int(time.time()) - 100,
            "exp": int(time.time()) - 10,
            "jti": "expired-jti",
        },
        jwt_utils.secret,
        algorithm="HS256",
    )
    res = await client.get(
        "/user/me",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_revoked_token_rejected(client: AsyncClient, admin_token: str):
    from sqlalchemy import select

    from common.sqlsession import async_session
    from routes.user import service as user_service
    from routes.user.model import Token

    async with async_session() as conn:
        stmt = select(Token).where(Token.token == admin_token)
        row = (await conn.execute(stmt)).scalar_one()
        await user_service.delete_token(conn, row)

    res = await client.get(
        "/user/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_cannot_create_admin_via_api(client: AsyncClient, admin_token: str):
    res = await client.post(
        "/user/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "hacker",
            "password": "password1",
            "permission": 100,
        },
    )
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_plain_user_cannot_list_users(
    client: AsyncClient, plain_user
):
    _, _, token, _ = plain_user
    res = await client.get(
        "/user/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_moderator_can_create_user(
    client: AsyncClient, moderator
):
    _, _, mod_token = moderator
    res = await client.post(
        "/user/",
        headers={"Authorization": f"Bearer {mod_token}"},
        json={
            "username": "newbie",
            "password": "newbie12",
            "permission": Permissions.USER,
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["username"] == "newbie"


@pytest.mark.asyncio
async def test_reset_password_then_login(
    client: AsyncClient, admin_token: str, plain_user
):
    _, _, _, idx = plain_user
    res = await client.post(
        f"/user/{idx}/reset_password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"new_password": "newpass99"},
    )
    assert res.status_code == 200, res.text

    bad = await client.post(
        "/user/auth",
        json={
            "username": "normaluser",
            "password": "userpass1",
            "keep_logged_in": False,
        },
    )
    assert bad.status_code == 401

    ok = await client.post(
        "/user/auth",
        json={
            "username": "normaluser",
            "password": "newpass99",
            "keep_logged_in": False,
        },
    )
    assert ok.status_code == 200

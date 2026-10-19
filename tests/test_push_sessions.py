"""로그인 토큰이 사라지면 묶인 FCM 행도 함께 사라진다 (logout, 만료, 개수 제한, 비밀번호, 사용자 삭제)."""
import time

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from common.sqlsession import async_session
from routes.fcm.model import FCMToken
from routes.user.model import Token
from tests.conftest import _login


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register(client, bearer, fcm):
    res = await client.post("/fcm/token", json={"fcm_token": fcm}, headers=_auth(bearer))
    assert res.status_code == 200, res.text


async def _fcm_rows() -> set[str]:
    async with async_session() as s:
        return set((await s.execute(select(FCMToken.fcm_token))).scalars().all())


async def _login_rows(user_idx: int) -> list[str]:
    async with async_session() as s:
        res = await s.execute(select(Token.token).where(Token.user_idx == user_idx))
        return list(res.scalars().all())


# --- POST /user/logout ---


@pytest.mark.asyncio
async def test_logout_deletes_login_token_and_bound_fcm(client: AsyncClient, plain_user):
    bearer, idx = plain_user[2], plain_user[3]
    other = await _login(client, "normaluser", "userpass1", keep=True)
    await _register(client, bearer, "this-device")
    await _register(client, other, "other-device")

    res = await client.post("/user/logout", headers=_auth(bearer))
    assert res.status_code == 200, res.text
    assert res.json()["data"] == {"logged_out": True, "fcm_removed": False}

    assert await _fcm_rows() == {"other-device"}
    assert await _login_rows(idx) == [other]
    again = await client.get("/user/me", headers=_auth(bearer))
    assert again.status_code == 401  # token gone: repeat logout is 401 as well
    assert (await client.post("/user/logout", headers=_auth(bearer))).status_code == 401


@pytest.mark.asyncio
async def test_logout_with_fcm_token_removes_owned_unbound_row(
    client: AsyncClient, admin_token: str, plain_user
):
    bearer = plain_user[2]
    # Legacy-style row owned by the caller but bound to a different login.
    other = await _login(client, "normaluser", "userpass1", keep=True)
    await _register(client, other, "mine")
    await _register(client, admin_token, "admins")

    res = await client.post("/user/logout", json={"fcm_token": "mine"}, headers=_auth(bearer))
    assert res.status_code == 200, res.text
    assert res.json()["data"] == {"logged_out": True, "fcm_removed": True}
    assert await _fcm_rows() == {"admins"}

    # Someone else's token in the body is ignored.
    second = await _login(client, "normaluser", "userpass1")
    res = await client.post("/user/logout", json={"fcm_token": "admins"}, headers=_auth(second))
    assert res.json()["data"] == {"logged_out": True, "fcm_removed": False}
    assert await _fcm_rows() == {"admins"}


@pytest.mark.asyncio
async def test_logout_requires_auth(client: AsyncClient):
    res = await client.post("/user/logout")
    assert res.status_code in (400, 401)


# --- cascades on other login-token deletions ---


@pytest.mark.asyncio
async def test_expired_sweep_removes_bound_fcm(client: AsyncClient, plain_user):
    await _register(client, plain_user[2], "dev")
    async with async_session() as s:
        login = (await s.execute(select(Token).where(Token.token == plain_user[2]))).scalars().one()
        login.exp = int(time.time()) - 10
        await s.commit()
    await _login(client, "admin", "adminpass1")  # any login sweeps expired tokens
    assert await _fcm_rows() == set()


@pytest.mark.asyncio
async def test_login_cap_is_10_and_prunes_bound_fcm(client: AsyncClient, plain_user):
    idx = plain_user[3]
    await _register(client, plain_user[2], "oldest-device")
    for _ in range(9):
        await _login(client, "normaluser", "userpass1", keep=True)
    assert len(await _login_rows(idx)) == 10
    assert await _fcm_rows() == {"oldest-device"}
    await _login(client, "normaluser", "userpass1", keep=True)  # 11th
    rows = await _login_rows(idx)
    assert len(rows) == 10 and plain_user[2] not in rows
    assert await _fcm_rows() == set()


@pytest.mark.asyncio
async def test_fcm_cap_is_10_per_user(client: AsyncClient, plain_user):
    for i in range(11):
        await _register(client, plain_user[2], f"dev-{i}")
    rows = await _fcm_rows()
    assert len(rows) == 10 and "dev-0" not in rows


@pytest.mark.asyncio
async def test_reset_password_revokes_logins_and_fcm(
    client: AsyncClient, admin_token: str, plain_user
):
    await _register(client, plain_user[2], "dev")
    await _register(client, admin_token, "admin-dev")
    res = await client.post(
        f"/user/{plain_user[3]}/reset_password",
        headers=_auth(admin_token),
        json={"new_password": "newpass99"},
    )
    assert res.status_code == 200, res.text
    assert await _login_rows(plain_user[3]) == []
    assert await _fcm_rows() == {"admin-dev"}
    assert (await client.get("/user/me", headers=_auth(plain_user[2]))).status_code == 401


@pytest.mark.asyncio
async def test_password_change_via_patch_revokes_other_logins(
    client: AsyncClient, admin_token: str, plain_user
):
    await _register(client, plain_user[2], "user-dev")
    other_admin = await _login(client, "admin", "adminpass1", keep=True)
    await _register(client, other_admin, "admin-other")
    await _register(client, admin_token, "admin-here")

    # Change another user's password: all their logins go.
    res = await client.patch(
        f"/user/{plain_user[3]}", headers=_auth(admin_token), json={"password": "newpass99"}
    )
    assert res.status_code == 200, res.text
    assert await _login_rows(plain_user[3]) == []

    # Change own password: the session doing it survives, the others go.
    res = await client.patch("/user/1", headers=_auth(admin_token), json={"password": "newadmin1"})
    assert res.status_code == 200, res.text
    assert await _login_rows(1) == [admin_token]
    assert await _fcm_rows() == {"admin-here"}
    assert (await client.get("/user/me", headers=_auth(admin_token))).status_code == 200


@pytest.mark.asyncio
async def test_patch_without_password_keeps_logins(
    client: AsyncClient, admin_token: str, plain_user
):
    await _register(client, plain_user[2], "dev")
    res = await client.patch(
        f"/user/{plain_user[3]}", headers=_auth(admin_token), json={"username": "renamed"}
    )
    assert res.status_code == 200, res.text
    assert await _login_rows(plain_user[3]) == [plain_user[2]]
    assert await _fcm_rows() == {"dev"}


@pytest.mark.asyncio
async def test_user_delete_removes_logins_and_fcm(
    client: AsyncClient, admin_token: str, plain_user
):
    await _register(client, plain_user[2], "dev")
    async with async_session() as s:  # legacy unbound row of the same user
        s.add(FCMToken(fcm_token="legacy", user_idx=plain_user[3]))
        await s.commit()
    res = await client.delete(f"/user/{plain_user[3]}", headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    assert await _login_rows(plain_user[3]) == []
    assert await _fcm_rows() == set()

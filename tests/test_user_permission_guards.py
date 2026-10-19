"""Permission hierarchy on user management (Admin=80 must not touch Super Admin=100 or peers)."""
import pytest_asyncio
from httpx import AsyncClient

from common.enums import Permissions
from common.security import hash_password
from common.sqlsession import async_session
from routes.user import model as user_model
from routes.user.service import get_user_byid
from tests.conftest import _login

SUPER_IDX = 1  # seeded by conftest (permission 100)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make(username: str, permission: int) -> int:
    async with async_session() as s:
        u = user_model.User(
            username=username, password=hash_password("password1"), permission=permission
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u.idx


async def _perm(idx: int) -> int | None:
    async with async_session() as s:
        try:
            return (await get_user_byid(s, idx)).permission
        except Exception:
            return None


@pytest_asyncio.fixture
async def admin80(client: AsyncClient):
    """(idx, token) of an Admin (80)."""
    idx = await _make("admin80", Permissions.MODERATOR)
    return idx, await _login(client, "admin80", "password1")


@pytest_asyncio.fixture
async def other_admin(admin80):
    return await _make("admin80b", Permissions.MODERATOR)


@pytest_asyncio.fixture
async def member():
    return await _make("member1", Permissions.USER)


# --- Admin -> Super Admin ---

async def test_admin_cannot_patch_super_admin(client, admin80):
    res = await client.patch(f"/user/{SUPER_IDX}", headers=_auth(admin80[1]), json={"username": "pwned"})
    assert res.status_code == 403
    assert res.json()["message"]
    assert await _perm(SUPER_IDX) == 100


async def test_admin_cannot_reset_super_admin_password(client, admin80):
    res = await client.post(
        f"/user/{SUPER_IDX}/reset_password", headers=_auth(admin80[1]), json={"new_password": "hijacked1"}
    )
    assert res.status_code == 403
    res = await client.post("/user/auth", json={"username": "admin", "password": "adminpass1"})
    assert res.status_code == 200


async def test_admin_cannot_delete_super_admin(client, admin80):
    res = await client.delete(f"/user/{SUPER_IDX}", headers=_auth(admin80[1]))
    assert res.status_code == 403
    assert await _perm(SUPER_IDX) == 100


# --- Admin -> Admin ---

async def test_admin_cannot_touch_other_admin(client, admin80, other_admin):
    h = _auth(admin80[1])
    assert (await client.patch(f"/user/{other_admin}", headers=h, json={"username": "renamed"})).status_code == 403
    assert (
        await client.post(f"/user/{other_admin}/reset_password", headers=h, json={"new_password": "hijacked1"})
    ).status_code == 403
    assert (await client.delete(f"/user/{other_admin}", headers=h)).status_code == 403
    assert await _perm(other_admin) == 80


# --- Admin -> Member (allowed) ---

async def test_admin_can_manage_member(client, admin80, member):
    h = _auth(admin80[1])
    assert (await client.patch(f"/user/{member}", headers=h, json={"username": "member2"})).status_code == 200
    assert (
        await client.post(f"/user/{member}/reset_password", headers=h, json={"new_password": "newpass99"})
    ).status_code == 200
    assert (await client.patch(f"/user/{member}", headers=h, json={"permission": 80})).status_code == 200
    assert await _perm(member) == 80
    victim = await _make("victim1", 0)
    assert (await client.delete(f"/user/{victim}", headers=h)).status_code == 200
    assert await _perm(victim) is None


# --- Super Admin -> Admin (allowed) ---

async def test_super_admin_can_manage_admin(client, admin_token, admin80):
    h = _auth(admin_token)
    idx = admin80[0]
    assert (await client.patch(f"/user/{idx}", headers=h, json={"permission": 0})).status_code == 200
    assert await _perm(idx) == 0
    assert (
        await client.post(f"/user/{idx}/reset_password", headers=h, json={"new_password": "newpass99"})
    ).status_code == 200
    assert (await client.delete(f"/user/{idx}", headers=h)).status_code == 200
    assert await _perm(idx) is None


# --- self ---

async def test_self_promotion_forbidden(client, admin80):
    idx, token = admin80
    res = await client.patch(f"/user/{idx}", headers=_auth(token), json={"permission": 100})
    assert res.status_code == 403
    assert await _perm(idx) == 80


async def test_self_permission_change_forbidden_even_demotion(client, admin80):
    idx, token = admin80
    res = await client.patch(f"/user/{idx}", headers=_auth(token), json={"permission": 0})
    assert res.status_code == 403
    assert await _perm(idx) == 80


async def test_self_unchanged_permission_echo_is_ok(client, admin80):
    idx, token = admin80
    res = await client.patch(
        f"/user/{idx}", headers=_auth(token), json={"username": "echo80", "permission": 80}
    )
    assert res.status_code == 200, res.text


async def test_self_username_password_and_reset_allowed(client, admin80):
    idx, token = admin80
    h = _auth(token)
    assert (await client.patch(f"/user/{idx}", headers=h, json={"username": "renamed80"})).status_code == 200
    assert (await client.patch(f"/user/{idx}", headers=h, json={"password": "newpass99"})).status_code == 200
    assert (
        await client.post(f"/user/{idx}/reset_password", headers=h, json={"new_password": "newpass88"})
    ).status_code == 200
    assert (await client.get("/user/me", headers=h)).status_code == 200


async def test_self_delete_forbidden(client, admin80, admin_token):
    assert (await client.delete(f"/user/{admin80[0]}", headers=_auth(admin80[1]))).status_code == 403
    assert (await client.delete(f"/user/{SUPER_IDX}", headers=_auth(admin_token))).status_code == 403
    assert await _perm(admin80[0]) == 80
    assert await _perm(SUPER_IDX) == 100


# --- permission values ---

async def test_create_super_admin_forbidden_for_everyone(client, admin_token, admin80):
    for tok in (admin_token, admin80[1]):
        res = await client.post(
            "/user/", headers=_auth(tok), json={"username": "hacker", "password": "password1", "permission": 100}
        )
        assert res.status_code == 403, res.text
        assert res.json()["message"]


async def test_admin_can_create_admin_and_member(client, admin80):
    h = _auth(admin80[1])
    for name, perm in (("newadmin", 80), ("newmember", 0)):
        res = await client.post(
            "/user/", headers=h, json={"username": name, "password": "password1", "permission": perm}
        )
        assert res.status_code == 200, res.text
        assert res.json()["data"]["permission"] == perm


async def test_promote_to_100_forbidden(client, admin_token, admin80, member):
    for tok in (admin_token, admin80[1]):
        res = await client.patch(f"/user/{member}", headers=_auth(tok), json={"permission": 100})
        assert res.status_code == 403, res.text
    assert await _perm(member) == 0


async def test_permission_above_caller_forbidden(client, admin80, member):
    res = await client.patch(f"/user/{member}", headers=_auth(admin80[1]), json={"permission": 90})
    assert res.status_code == 403
    res = await client.post(
        "/user/", headers=_auth(admin80[1]), json={"username": "above", "password": "password1", "permission": 90}
    )
    assert res.status_code == 403
    assert await _perm(member) == 0


# --- ordering / member caller ---

async def test_missing_target_is_404_first(client, admin80):
    h = _auth(admin80[1])
    assert (await client.patch("/user/9999", headers=h, json={"permission": 100})).status_code == 404
    assert (await client.delete("/user/9999", headers=h)).status_code == 404
    assert (
        await client.post("/user/9999/reset_password", headers=h, json={"new_password": "newpass99"})
    ).status_code == 404


async def test_member_caller_forbidden(client, plain_user, admin80):
    h = _auth(plain_user[2])
    assert (await client.patch(f"/user/{admin80[0]}", headers=h, json={"username": "zzz"})).status_code == 403
    assert (await client.delete(f"/user/{admin80[0]}", headers=h)).status_code == 403
    assert (
        await client.post("/user/", headers=h, json={"username": "abcd", "password": "password1"})
    ).status_code == 403

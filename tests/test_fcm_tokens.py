import pytest
from httpx import AsyncClient
from sqlalchemy import select

from common.sqlsession import async_session
from routes.fcm.model import FCMToken


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _rows(token: str):
    async with async_session() as s:
        res = await s.execute(select(FCMToken).where(FCMToken.fcm_token == token))
        return res.scalars().all()


async def _register(client, auth_token, fcm="tok-1"):
    return await client.post(
        "/fcm/token", json={"fcm_token": fcm}, headers=_auth(auth_token)
    )


async def _unregister(client, auth_token, fcm="tok-1"):
    return await client.request(
        "DELETE", "/fcm/token", json={"fcm_token": fcm}, headers=_auth(auth_token)
    )


@pytest.mark.asyncio
async def test_register_twice_is_200(client: AsyncClient, plain_user):
    first = await _register(client, plain_user[2])
    second = await _register(client, plain_user[2])
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["data"]["idx"] == first.json()["data"]["idx"]
    assert len(await _rows("tok-1")) == 1


@pytest.mark.asyncio
async def test_register_reassigns_other_user(
    client: AsyncClient, admin_token: str, plain_user
):
    assert (await _register(client, admin_token)).status_code == 200
    res = await _register(client, plain_user[2])
    assert res.status_code == 200, res.text
    rows = await _rows("tok-1")
    assert len(rows) == 1
    assert rows[0].user_idx == plain_user[3]


@pytest.mark.asyncio
async def test_unregister_own_token(client: AsyncClient, plain_user):
    await _register(client, plain_user[2])
    res = await _unregister(client, plain_user[2])
    assert res.status_code == 200, res.text
    assert res.json()["data"] == {"removed": True}
    assert await _rows("tok-1") == []


@pytest.mark.asyncio
async def test_unregister_other_users_token_noop(
    client: AsyncClient, admin_token: str, plain_user
):
    await _register(client, admin_token)
    res = await _unregister(client, plain_user[2])
    assert res.status_code == 200, res.text
    assert res.json()["data"] == {"removed": False}
    assert len(await _rows("tok-1")) == 1


@pytest.mark.asyncio
async def test_reassigned_token_survives_pruning(
    client: AsyncClient, admin_token: str, plain_user
):
    # The token that will be reassigned has the lowest idx.
    assert (await _register(client, admin_token, "old")).status_code == 200
    for t in ("a", "b", "c"):
        assert (await _register(client, plain_user[2], t)).status_code == 200
    res = await _register(client, plain_user[2], "old")
    assert res.status_code == 200, res.text
    rows = await _rows("old")
    assert len(rows) == 1 and rows[0].user_idx == plain_user[3]
    assert res.json()["data"]["idx"] == rows[0].idx
    assert await _rows("a") == []  # oldest of the user's tokens pruned

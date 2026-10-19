import time
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from common.sqlsession import async_session
from routes.fcm import service as fcm_service
from routes.fcm.model import FCMToken
from routes.user.model import Token
from tests.conftest import _login


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
    for t in "abcdefghij":  # fill the per-user cap (10)
        assert (await _register(client, plain_user[2], t)).status_code == 200
    res = await _register(client, plain_user[2], "old")
    assert res.status_code == 200, res.text
    rows = await _rows("old")
    assert len(rows) == 1 and rows[0].user_idx == plain_user[3]
    assert res.json()["data"]["idx"] == rows[0].idx
    assert await _rows("a") == []  # oldest of the user's tokens pruned


# --- B1: FCM rows bound to the login token that registered them ---


async def _login_row(bearer: str):
    async with async_session() as s:
        res = await s.execute(select(Token).where(Token.token == bearer))
        return res.scalars().one()


async def _deliverable(userid: int) -> set[str]:
    async with async_session() as s:
        return {t.fcm_token for t in await fcm_service.get_fcm_tokens(s, userid)}


@pytest.mark.asyncio
async def test_register_binds_row_to_login_token(client: AsyncClient, plain_user):
    assert (await _register(client, plain_user[2])).status_code == 200
    row = (await _rows("tok-1"))[0]
    assert row.token_idx == (await _login_row(plain_user[2])).idx
    assert await _deliverable(plain_user[3]) == {"tok-1"}


@pytest.mark.asyncio
async def test_register_response_shape_unchanged(client: AsyncClient, plain_user):
    res = await _register(client, plain_user[2])
    assert set(res.json()["data"]) == {"idx", "last_delivery", "user_idx"}


@pytest.mark.asyncio
async def test_expired_login_token_not_delivered(client: AsyncClient, plain_user):
    await _register(client, plain_user[2])
    async with async_session() as s:
        login = (await s.execute(select(Token).where(Token.token == plain_user[2]))).scalars().one()
        login.exp = int(time.time()) - 10
        await s.commit()
    assert await _deliverable(plain_user[3]) == set()


@pytest.mark.asyncio
async def test_deleted_login_token_not_delivered(client: AsyncClient, plain_user):
    await _register(client, plain_user[2])
    async with async_session() as s:
        await s.execute(delete(Token).where(Token.token == plain_user[2]))
        await s.commit()
    assert await _deliverable(plain_user[3]) == set()


@pytest.mark.asyncio
async def test_legacy_unbound_row_delivered_until_stale(plain_user):
    now = datetime.now(UTC)
    async with async_session() as s:
        s.add(FCMToken(fcm_token="fresh", user_idx=plain_user[3], last_delivery=now))
        s.add(FCMToken(fcm_token="stale", user_idx=plain_user[3],
                       last_delivery=now - timedelta(days=31)))
        s.add(FCMToken(fcm_token="never", user_idx=plain_user[3], last_delivery=None))
        await s.commit()
    assert await _deliverable(plain_user[3]) == {"fresh"}


@pytest.mark.asyncio
async def test_sweep_prunes_stale_legacy_rows(client: AsyncClient, plain_user):
    now = datetime.now(UTC)
    async with async_session() as s:
        s.add(FCMToken(fcm_token="fresh", user_idx=plain_user[3], last_delivery=now))
        s.add(FCMToken(fcm_token="stale", user_idx=plain_user[3],
                       last_delivery=now - timedelta(days=31)))
        await s.commit()
    await _login(client, "normaluser", "userpass1")  # login runs the sweep
    assert len(await _rows("fresh")) == 1
    assert await _rows("stale") == []


@pytest.mark.asyncio
async def test_reregister_from_other_login_rebinds(client: AsyncClient, plain_user):
    await _register(client, plain_user[2])
    second = await _login(client, "normaluser", "userpass1", keep=True)
    assert (await _register(client, second)).status_code == 200
    rows = await _rows("tok-1")
    assert len(rows) == 1
    assert rows[0].token_idx == (await _login_row(second)).idx

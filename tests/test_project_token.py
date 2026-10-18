import pytest
from common.sqlsession import async_session
from httpx import AsyncClient
from routes.user.model import User
from sqlalchemy import select


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _mod_idx(username: str) -> int:
    async with async_session() as s:
        u = (
            await s.execute(select(User).where(User.username == username))
        ).scalar_one()
        return u.idx


async def _grant(client, admin_token, moderator, pid):
    res = await client.post(
        "/project/perm",
        headers=_auth(admin_token),
        json={"userid": await _mod_idx(moderator[0]), "projectid": pid},
    )
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_get_token_moderator_needs_project_access(
    client: AsyncClient, admin_token: str, moderator, project_with_key
):
    _, token, pid = project_with_key
    res = await client.get(f"/project/{pid}/token", headers=_auth(moderator[2]))
    assert res.status_code == 403
    await _grant(client, admin_token, moderator, pid)
    res = await client.get(f"/project/{pid}/token", headers=_auth(moderator[2]))
    assert res.status_code == 200
    assert res.json()["data"]["token"] == token


@pytest.mark.asyncio
async def test_get_token_matches_created(
    client: AsyncClient, admin_token: str, moderator, project_with_key
):
    _, token, pid = project_with_key
    await _grant(client, admin_token, moderator, pid)
    for caller in (admin_token, moderator[2]):
        res = await client.get(f"/project/{pid}/token", headers=_auth(caller))
        assert res.status_code == 200, res.text
        assert res.json()["data"]["token"] == token

    rot = await client.post(f"/project/{pid}/rotate-token", headers=_auth(admin_token))
    new_token = rot.json()["data"]["token"]
    res = await client.get(f"/project/{pid}/token", headers=_auth(admin_token))
    assert res.json()["data"]["token"] == new_token


@pytest.mark.asyncio
async def test_get_token_missing_project_404(client: AsyncClient, admin_token: str):
    res = await client.get("/project/9999/token", headers=_auth(admin_token))
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_token_forbidden_for_user(
    client: AsyncClient, plain_user, project_with_key
):
    res = await client.get(
        f"/project/{project_with_key[2]}/token", headers=_auth(plain_user[2])
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_list_projects_still_hides_token(
    client: AsyncClient, admin_token: str, project_with_key
):
    res = await client.get("/project/", headers=_auth(admin_token))
    assert res.status_code == 200
    items = res.json()["data"]
    assert items
    assert all("token" not in item for item in items)

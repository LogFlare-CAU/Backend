import pytest
from httpx import AsyncClient


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_token_matches_created(
    client: AsyncClient, admin_token: str, moderator, project_with_key
):
    _, token, pid = project_with_key
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

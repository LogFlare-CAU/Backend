"""Project CRUD / key / logfile path tests."""
import pytest
from httpx import AsyncClient

from tests.conftest import FIXTURES


@pytest.mark.asyncio
async def test_create_and_list_projects(client: AsyncClient, admin_token: str):
    created = await client.post(
        "/project/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "alpha"},
    )
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["name"] == "alpha"
    assert data.get("token")
    assert len(data["token"]) >= 32

    listed = await client.get(
        "/project/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert listed.status_code == 200
    names = [p["name"] for p in listed.json()["data"]]
    assert "alpha" in names
    # list view must not leak tokens
    for p in listed.json()["data"]:
        assert "token" not in p or p.get("token") in (None, "")


@pytest.mark.asyncio
async def test_project_name_header_mismatch_forbidden(
    client: AsyncClient, project_with_key
):
    name, token, _ = project_with_key
    res = await client.post(
        "/log/error",
        headers={
            "Project": "not-" + name,
            "ProjectKey": f"Bearer {token}",
        },
        json={
            "errortype": "X",
            "level": "ERROR",
            "message": "nope",
            "test": False,
        },
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_rotate_project_token_invalidates_old(
    client: AsyncClient, admin_token: str, project_with_key
):
    name, token, project_id = project_with_key
    rot = await client.post(
        f"/project/{project_id}/rotate-token",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert rot.status_code == 200
    new_token = rot.json()["data"]["token"]
    assert new_token != token

    old = await client.post(
        "/log/error",
        headers={"Project": name, "ProjectKey": f"Bearer {token}"},
        json={
            "errortype": "X",
            "level": "ERROR",
            "message": "old",
            "test": False,
        },
    )
    assert old.status_code == 401

    ok = await client.post(
        "/log/error",
        headers={"Project": name, "ProjectKey": f"Bearer {new_token}"},
        json={
            "errortype": "X",
            "level": "ERROR",
            "message": "new",
            "test": False,
        },
    )
    assert ok.status_code == 204


@pytest.mark.asyncio
async def test_add_logfile_inside_allowlist(
    client: AsyncClient, admin_token: str, project_with_key, sample_logfile
):
    _, _, project_id = project_with_key
    res = await client.post(
        f"/project/{project_id}/logfile",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "app.log", "path": str(sample_logfile)},
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["file_name"] == "app.log"


@pytest.mark.asyncio
async def test_add_logfile_outside_allowlist_forbidden(
    client: AsyncClient, admin_token: str, project_with_key, tmp_path
):
    _, _, project_id = project_with_key
    outside = tmp_path / "secrets.txt"
    outside.write_text("nope", encoding="utf-8")
    # Ensure outside is not under FIXTURES
    assert not str(outside.resolve()).startswith(str(FIXTURES.resolve()))

    res = await client.post(
        f"/project/{project_id}/logfile",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "evil", "path": str(outside)},
    )
    assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_plain_user_cannot_create_project(
    client: AsyncClient, plain_user
):
    _, _, token, _ = plain_user
    res = await client.post(
        "/project/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "denied"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_grant_project_perm_and_list(
    client: AsyncClient, admin_token: str, project_with_key, plain_user
):
    _, _, project_id = project_with_key
    _, _, user_token, user_idx = plain_user

    grant = await client.post(
        "/project/perm",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"userid": user_idx, "projectid": project_id},
    )
    assert grant.status_code == 200, grant.text

    listed = await client.get(
        "/project/",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert listed.status_code == 200
    names = [p["name"] for p in listed.json()["data"]]
    assert "demo-project" in names

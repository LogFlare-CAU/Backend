"""Log ingest / query / file read tests."""
import pytest
from httpx import AsyncClient


async def _ingest(client: AsyncClient, name: str, token: str, message: str):
    res = await client.post(
        "/log/error",
        headers={
            "Project": name,
            "ProjectKey": f"Bearer {token}",
        },
        json={
            "errortype": "ValueError",
            "level": "ERROR",
            "message": message,
            "test": False,
        },
    )
    assert res.status_code == 204, res.text
    return res


@pytest.mark.asyncio
async def test_health_envelope(client: AsyncClient):
    res = await client.get("/log/")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert "traceback" not in str(body.get("data"))


@pytest.mark.asyncio
async def test_post_log_error_with_project_key(client: AsyncClient, project_with_key):
    name, token, _ = project_with_key
    await _ingest(client, name, token, "boom")

    bad = await client.post(
        "/log/error",
        headers={
            "Project": name,
            "ProjectKey": "Bearer not-a-real-token",
        },
        json={
            "errortype": "ValueError",
            "level": "ERROR",
            "message": "boom",
            "test": False,
        },
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_log_error_test_flag_skips_persist(
    client: AsyncClient, admin_token: str, project_with_key
):
    name, token, project_id = project_with_key
    res = await client.post(
        "/log/error",
        headers={"Project": name, "ProjectKey": f"Bearer {token}"},
        json={
            "errortype": "T",
            "level": "ERROR",
            "message": "should-not-store",
            "test": True,
        },
    )
    assert res.status_code == 204

    listed = await client.get(
        "/log/error",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"project_id": project_id},
    )
    assert listed.status_code == 200
    messages = [e["message"] for e in listed.json()["data"]]
    assert "should-not-store" not in messages


@pytest.mark.asyncio
async def test_get_errors_for_admin(
    client: AsyncClient, admin_token: str, project_with_key
):
    name, token, project_id = project_with_key
    await _ingest(client, name, token, "err-a")
    await _ingest(client, name, token, "err-b")

    res = await client.get(
        "/log/error",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"project_id": project_id, "limit": 10},
    )
    assert res.status_code == 200, res.text
    messages = [e["message"] for e in res.json()["data"]]
    assert "err-a" in messages
    assert "err-b" in messages


@pytest.mark.asyncio
async def test_get_errors_denied_without_project_access(
    client: AsyncClient, plain_user, project_with_key
):
    name, token, project_id = project_with_key
    await _ingest(client, name, token, "secret-err")
    _, _, user_token, _ = plain_user

    res = await client.get(
        "/log/error",
        headers={"Authorization": f"Bearer {user_token}"},
        params={"project_id": project_id},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_get_errors_global_only_accessible_projects(
    client: AsyncClient,
    admin_token: str,
    plain_user,
    project_with_key,
):
    name, token, project_id = project_with_key
    await _ingest(client, name, token, "visible-if-granted")

    # second project the user will not get access to
    other = await client.post(
        "/project/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "other-project"},
    )
    other_data = other.json()["data"]
    await _ingest(client, other_data["name"], other_data["token"], "hidden-err")

    _, _, user_token, user_idx = plain_user
    await client.post(
        "/project/perm",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"userid": user_idx, "projectid": project_id},
    )

    res = await client.get(
        "/log/error",
        headers={"Authorization": f"Bearer {user_token}"},
        params={"limit": 50},
    )
    assert res.status_code == 200, res.text
    messages = [e["message"] for e in res.json()["data"]]
    assert "visible-if-granted" in messages
    assert "hidden-err" not in messages


@pytest.mark.asyncio
async def test_read_logfile_entries(
    client: AsyncClient, admin_token: str, project_with_key, sample_logfile
):
    _, _, project_id = project_with_key
    add = await client.post(
        f"/project/{project_id}/logfile",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "sample", "path": str(sample_logfile)},
    )
    assert add.status_code == 200, add.text
    logfile_id = add.json()["data"]["id"]

    res = await client.get(
        f"/log/{project_id}/{logfile_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"limit": 10, "sortby": "oldest"},
    )
    assert res.status_code == 200, res.text
    entries = res.json()["data"]
    assert len(entries) >= 2
    assert "INFO | hello" in entries[0]

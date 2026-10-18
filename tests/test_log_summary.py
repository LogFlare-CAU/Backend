from datetime import UTC, datetime, timedelta

import pytest
from common.sqlsession import async_session
from routes.logs.model import Errorlog

pytestmark = pytest.mark.asyncio


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


async def _insert(project_id, level, ago_hours):
    async with async_session() as s:
        s.add(
            Errorlog(
                project_id=project_id,
                level=level,
                message="m",
                timestamp=_now() - timedelta(hours=ago_hours),
            )
        )
        await s.commit()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _second_project(client, admin_token, name="other-project"):
    res = await client.post("/project/", headers=_auth(admin_token), json={"name": name})
    assert res.status_code == 200, res.text
    return res.json()["data"]["id"]


async def test_summary_counts_last_24h_only(client, admin_token, project_with_key):
    pid = project_with_key[2]
    await _insert(pid, "ERROR", 1)
    await _insert(pid, "WARNING", 23)
    await _insert(pid, "ERROR", 25)
    res = await client.get("/log/summary", headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["window_hours"] == 24
    assert data["counts"] == {
        "DEBUG": 0, "INFO": 0, "WARNING": 1, "ERROR": 1, "CRITICAL": 0,
    }
    assert data["since"].endswith("+00:00")


async def test_summary_counts_lowercase_levels(client, admin_token, project_with_key):
    pid = project_with_key[2]
    await _insert(pid, "error", 1)
    await _insert(pid, "Warn", 1)
    res = await client.get("/log/summary", headers=_auth(admin_token))
    counts = res.json()["data"]["counts"]
    assert counts["ERROR"] == 1
    assert sum(counts.values()) == 1


async def test_summary_hours_clamped(client, admin_token, project_with_key):
    res = await client.get("/log/summary?hours=9999", headers=_auth(admin_token))
    assert res.json()["data"]["window_hours"] == 168
    res = await client.get("/log/summary?hours=0", headers=_auth(admin_token))
    assert res.json()["data"]["window_hours"] == 1


async def test_summary_per_project(client, admin_token, project_with_key):
    a = project_with_key[2]
    b = await _second_project(client, admin_token)
    await _insert(a, "ERROR", 2)
    await _insert(a, "critical", 3)
    await _insert(a, "WARNING", 4)
    await _insert(a, "ERROR", 50)  # outside window, but older than the 2h one
    res = await client.get("/log/summary", headers=_auth(admin_token))
    projects = {p["project_id"]: p for p in res.json()["data"]["projects"]}
    assert set(projects) == {a, b}
    assert projects[a]["error_count"] == 2
    assert projects[a]["warning_count"] == 1
    assert projects[a]["last_error_at"] is not None
    assert projects[b] == {
        "project_id": b, "error_count": 0, "warning_count": 0, "last_error_at": None,
    }


async def test_summary_last_error_ignores_window(client, admin_token, project_with_key):
    a = project_with_key[2]
    await _insert(a, "ERROR", 50)
    res = await client.get("/log/summary", headers=_auth(admin_token))
    p = res.json()["data"]["projects"][0]
    assert p["error_count"] == 0
    assert p["last_error_at"] is not None


async def test_summary_filter_project_id(client, admin_token, project_with_key):
    a = project_with_key[2]
    b = await _second_project(client, admin_token)
    await _insert(a, "ERROR", 1)
    await _insert(b, "ERROR", 1)
    await _insert(b, "INFO", 1)
    res = await client.get(f"/log/summary?project_id={a}", headers=_auth(admin_token))
    data = res.json()["data"]
    assert [p["project_id"] for p in data["projects"]] == [a]
    assert data["counts"]["ERROR"] == 1
    assert data["counts"]["INFO"] == 0


async def test_summary_forbidden_project(client, admin_token, project_with_key, plain_user):
    a = project_with_key[2]
    b = await _second_project(client, admin_token)
    _, _, token, idx = plain_user
    await _insert(a, "ERROR", 1)
    await _insert(b, "ERROR", 1)
    res = await client.get(f"/log/summary?project_id={a}", headers=_auth(token))
    assert res.status_code == 403
    # grant access to b only
    res = await client.post(
        "/project/perm", headers=_auth(admin_token), json={"userid": idx, "projectid": b}
    )
    assert res.status_code == 200, res.text
    res = await client.get("/log/summary", headers=_auth(token))
    data = res.json()["data"]
    assert [p["project_id"] for p in data["projects"]] == [b]
    assert data["counts"]["ERROR"] == 1

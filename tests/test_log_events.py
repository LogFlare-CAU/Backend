from datetime import UTC, datetime, timedelta

import pytest
from common.sqlsession import async_session
from routes.logs.model import Errorlog
from routes.projects.model import LogFile

pytestmark = pytest.mark.asyncio


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _insert(project_id, message="m", errortype="T", level="ERROR",
                  ago_minutes=0, logfile_id=None):
    async with async_session() as s:
        e = Errorlog(
            project_id=project_id,
            errortype=errortype,
            level=level,
            message=message,
            logfile_id=logfile_id,
            timestamp=_now() - timedelta(minutes=ago_minutes),
        )
        s.add(e)
        await s.commit()
        await s.refresh(e)
        return e.id


async def _get(client, token, query=""):
    res = await client.get(f"/log/events?{query}", headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def test_events_grouped_counts(client, admin_token, project_with_key):
    pid = project_with_key[2]
    ids = [
        await _insert(pid, "boom", "E", ago_minutes=30),
        await _insert(pid, "boom", "E", ago_minutes=20),
        await _insert(pid, "boom", "E", ago_minutes=10),
    ]
    await _insert(pid, "other", "E", ago_minutes=40)
    data = await _get(client, admin_token)
    assert len(data["items"]) == 2
    first = data["items"][0]
    assert first["occurrences"] == 3
    assert first["id"] == ids[-1]
    assert first["first_seen"] < first["last_seen"]
    assert first["timestamp"] == first["last_seen"]
    assert "+" not in first["last_seen"] and not first["last_seen"].endswith("Z")
    assert data["next_cursor"] is None


async def test_events_ungrouped(client, admin_token, project_with_key):
    pid = project_with_key[2]
    await _insert(pid, "boom", ago_minutes=2)
    await _insert(pid, "boom", ago_minutes=1)
    data = await _get(client, admin_token, "grouped=false")
    assert [i["occurrences"] for i in data["items"]] == [1, 1]
    assert all(i["first_seen"] == i["last_seen"] == i["timestamp"] for i in data["items"])


async def test_events_grouped_null_errortype(client, admin_token, project_with_key):
    pid = project_with_key[2]
    await _insert(pid, "x", None)
    await _insert(pid, "x", None)
    await _insert(pid, "x", "T")
    data = await _get(client, admin_token)
    assert sorted(i["occurrences"] for i in data["items"]) == [1, 2]


async def test_events_min_level(client, admin_token, project_with_key):
    pid = project_with_key[2]
    await _insert(pid, "a", level="INFO")
    await _insert(pid, "b", level="WARNING")
    await _insert(pid, "c", level="ERROR")
    await _insert(pid, "d", level="CRITICAL")
    await _insert(pid, "e", level="error")
    data = await _get(client, admin_token, "min_level=ERROR")
    assert sorted(i["message"] for i in data["items"]) == ["c", "d", "e"]


async def test_events_logfile_filter_and_name(client, admin_token, project_with_key):
    pid = project_with_key[2]
    async with async_session() as s:
        lf = LogFile(project_id=pid, file_path="/x/app.log", file_name="app.log")
        s.add(lf)
        await s.commit()
        await s.refresh(lf)
        lfid = lf.id
    await _insert(pid, "linked", logfile_id=lfid)
    await _insert(pid, "unlinked")
    data = await _get(client, admin_token, f"logfile_id={lfid}")
    assert [i["message"] for i in data["items"]] == ["linked"]
    assert data["items"][0]["logfile_name"] == "app.log"
    assert data["items"][0]["logfile_id"] == lfid
    data = await _get(client, admin_token)
    names = {i["message"]: i["logfile_name"] for i in data["items"]}
    assert names == {"linked": "app.log", "unlinked": None}


async def test_events_sort_highest(client, admin_token, project_with_key):
    pid = project_with_key[2]
    await _insert(pid, "w", level="WARNING", ago_minutes=1)
    await _insert(pid, "c", level="CRITICAL", ago_minutes=5)
    await _insert(pid, "e", level="error", ago_minutes=3)
    data = await _get(client, admin_token, "sort=highest")
    assert [i["level"] for i in data["items"]] == ["CRITICAL", "ERROR", "WARNING"]
    data = await _get(client, admin_token, "sort=lowest")
    assert data["items"][0]["level"] == "WARNING"
    data = await _get(client, admin_token, "sort=oldest")
    assert data["items"][0]["message"] == "c"


async def test_events_q_search(client, admin_token, project_with_key):
    pid = project_with_key[2]
    await _insert(pid, "Connection POOL exhausted", "DbError")
    await _insert(pid, "unrelated", "OtherError")
    data = await _get(client, admin_token, "q=pool")
    assert [i["message"] for i in data["items"]] == ["Connection POOL exhausted"]
    data = await _get(client, admin_token, "q=othererr")
    assert [i["message"] for i in data["items"]] == ["unrelated"]


async def test_events_since_until(client, admin_token, project_with_key):
    pid = project_with_key[2]
    await _insert(pid, "old", ago_minutes=120)
    await _insert(pid, "new", ago_minutes=1)
    since = (_now() - timedelta(minutes=60)).isoformat()
    data = await _get(client, admin_token, f"since={since}")
    assert [i["message"] for i in data["items"]] == ["new"]
    data = await _get(client, admin_token, f"until={since}")
    assert [i["message"] for i in data["items"]] == ["old"]


async def test_events_cursor_no_duplicates_after_insert(
        client, admin_token, project_with_key
):
    pid = project_with_key[2]
    for n in range(5):
        await _insert(pid, f"g{n}", ago_minutes=50 - n * 10)
    page1 = await _get(client, admin_token, "limit=2")
    assert len(page1["items"]) == 2 and page1["next_cursor"]
    new_id = await _insert(pid, "brand-new")
    seen = [i["id"] for i in page1["items"]]
    cursor = page1["next_cursor"]
    pages = 0
    while cursor:
        page = await _get(client, admin_token, f"limit=2&cursor={cursor}")
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
        pages += 1
    assert pages == 2
    assert len(seen) == len(set(seen)) == 5
    assert new_id not in seen


async def test_events_invalid_cursor(client, admin_token, project_with_key):
    res = await client.get("/log/events?cursor=%%%", headers=_auth(admin_token))
    assert res.status_code == 400
    res = await client.get("/log/events?cursor=bm90anNvbg", headers=_auth(admin_token))
    assert res.status_code == 400


async def test_events_limit_bounds(client, admin_token, project_with_key):
    for limit in (0, 201):
        res = await client.get(f"/log/events?limit={limit}", headers=_auth(admin_token))
        assert res.status_code == 422


async def test_events_forbidden_project(client, admin_token, project_with_key, plain_user):
    a = project_with_key[2]
    _, _, token, _ = plain_user
    await _insert(a, "secret")
    res = await client.get(f"/log/events?project_id={a}", headers=_auth(token))
    assert res.status_code == 403
    data = await _get(client, token)
    assert data["items"] == []


async def test_events_since_respects_offset(client, admin_token, project_with_key):
    pid = project_with_key[2]
    async with async_session() as s:
        s.add(Errorlog(project_id=pid, errortype="T", level="ERROR", message="tz",
                       timestamp=datetime(2026, 1, 1, 3, 0, 0)))
        await s.commit()
    # 11:00+09:00 == 02:00Z -> 03:00Z row included
    data = await _get(client, admin_token, "since=2026-01-01T11:00:00%2B09:00")
    assert [i["message"] for i in data["items"]] == ["tz"]
    # 13:00+09:00 == 04:00Z -> excluded
    data = await _get(client, admin_token, "since=2026-01-01T13:00:00%2B09:00")
    assert data["items"] == []
    # until 11:00+09:00 == 02:00Z -> excluded; 13:00+09:00 -> included
    data = await _get(client, admin_token, "until=2026-01-01T11:00:00%2B09:00")
    assert data["items"] == []
    data = await _get(client, admin_token, "until=2026-01-01T13:00:00%2B09:00")
    assert len(data["items"]) == 1


async def test_events_q_escapes_like_wildcards(client, admin_token, project_with_key):
    pid = project_with_key[2]
    await _insert(pid, "user_id missing", None)
    await _insert(pid, "userXid missing", None)
    await _insert(pid, "100% done", None)
    data = await _get(client, admin_token, "q=user_id")
    assert [i["message"] for i in data["items"]] == ["user_id missing"]
    data = await _get(client, admin_token, "q=%25")
    assert [i["message"] for i in data["items"]] == ["100% done"]

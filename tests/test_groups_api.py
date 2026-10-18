"""GET/PATCH /group tests."""
from datetime import UTC, datetime, timedelta

import pytest

from common.sqlsession import async_session
from routes.collector.parse import Entry
from routes.groups.service import record_entry
from routes.projects.model import Project


def _h(t):
    return {"Authorization": f"Bearer {t}"}


async def seed(counts, prefix="m"):
    async with async_session() as s:
        p = Project(name=f"proj-{prefix}", token=None)
        s.add(p)
        await s.commit()
        for i, n in enumerate(counts):
            for k in range(n):
                ts = datetime.now(UTC) - timedelta(minutes=n * 10 - k)
                await record_entry(s, p.id, p.name, Entry("ERROR", None, f"{prefix}{i} boom", ts))
        await s.commit()
        return p.id


@pytest.mark.asyncio
async def test_group_list_requires_moderator(client, plain_user, admin_token):
    assert (await client.get("/group")).status_code in (400, 401)
    assert (await client.get("/group", headers=_h(plain_user[2]))).status_code == 403
    res = await client.get("/group", headers=_h(admin_token))
    assert res.status_code == 200 and res.json()["data"] == []


@pytest.mark.asyncio
async def test_group_sort_and_ignore(client, admin_token):
    await seed([1, 5, 3], "s")
    h = _h(admin_token)
    items = (await client.get("/group?sort=count", headers=h)).json()["data"]
    assert [g["count"] for g in items] == [5, 3, 1]
    assert items[0]["project_name"] == "proj-s"
    new = (await client.get("/group?sort=new", headers=h)).json()["data"]
    assert [g["count"] for g in new] == [1, 3, 5]
    gid = items[0]["id"]
    r = await client.patch(f"/group/{gid}", headers=h, json={"ignored": True})
    assert r.status_code == 200 and r.json()["data"]["ignored"] is True
    assert [g["count"] for g in (await client.get("/group?sort=count", headers=h)).json()["data"]] == [3, 1]
    inc = (await client.get("/group?sort=count&include_ignored=true", headers=h)).json()["data"]
    assert [g["count"] for g in inc] == [5, 3, 1]


@pytest.mark.asyncio
async def test_group_detail_recent_20(client, admin_token):
    await seed([25], "d")
    h = _h(admin_token)
    gid = (await client.get("/group", headers=h)).json()["data"][0]["id"]
    data = (await client.get(f"/group/{gid}", headers=h)).json()["data"]
    assert len(data["recent"]) == 20
    ts = [r["timestamp"] for r in data["recent"]]
    assert ts == sorted(ts, reverse=True)
    assert (await client.get("/group/9999", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_group_timestamps_are_utc_aware(client, admin_token):
    await seed([2], "t")
    h = _h(admin_token)
    item = (await client.get("/group", headers=h)).json()["data"][0]
    assert item["first_seen"].endswith("+00:00") and item["last_seen"].endswith("+00:00")
    d = (await client.get(f"/group/{item['id']}", headers=h)).json()["data"]
    assert d["first_seen"].endswith("+00:00")
    assert all(r["timestamp"].endswith("+00:00") for r in d["recent"])

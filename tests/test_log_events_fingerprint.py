"""/log/events grouping by production's error fingerprint (falls back for NULL fingerprints)."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from common.sqlsession import async_session
from routes.groups.model import ErrorGroup
from routes.logs.model import Errorlog

pytestmark = pytest.mark.asyncio


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _insert(project_id, message, fingerprint=None, errortype="E", level="ERROR", ago=0):
    async with async_session() as s:
        e = Errorlog(
            project_id=project_id,
            errortype=errortype,
            level=level,
            message=message,
            fingerprint=fingerprint,
            timestamp=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=ago),
        )
        s.add(e)
        await s.commit()
        return e.id


async def _events(client, token, **params):
    res = await client.get("/log/events", headers=_auth(token), params=params)
    assert res.status_code == 200, res.text
    return res.json()["data"]["items"]


async def _ingest(client, name, key, message, level="ERROR"):
    res = await client.post(
        "/log/error",
        headers={"Project": name, "ProjectKey": f"Bearer {key}"},
        json={"errortype": "LookupError", "level": level, "message": message},
    )
    assert res.status_code == 204, res.text


async def test_same_fingerprint_different_messages_is_one_group(client, admin_token, project_with_key):
    pid = project_with_key[2]
    a = await _insert(pid, "user 12 not found", "fp-1", ago=10)
    b = await _insert(pid, "user 34 not found", "fp-1", ago=5)
    await _insert(pid, "other failure", "fp-2", ago=1)
    items = await _events(client, admin_token)
    assert len(items) == 2
    grp = next(i for i in items if i["id"] == b)
    assert grp["occurrences"] == 2
    assert grp["message"] == "user 34 not found"  # latest row of the group
    assert grp["first_seen"] < grp["last_seen"] == grp["timestamp"]

    res = await client.get(f"/log/events/{a}", headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    d = res.json()["data"]
    assert d["id"] == a and d["message"] == "user 34 not found"
    assert d["occurrences"] == 2 and d["recent_ids"] == [b]
    assert d["occurred_at"] == grp["first_seen"]


async def test_null_fingerprint_rows_fall_back_to_legacy_key(client, admin_token, project_with_key):
    pid = project_with_key[2]
    l1 = await _insert(pid, "legacy boom", None, ago=9)
    l2 = await _insert(pid, "legacy boom", None, ago=8)
    await _insert(pid, "legacy boom", None, errortype="Other", ago=7)
    # same text but fingerprinted -> not merged with the legacy rows
    f1 = await _insert(pid, "legacy boom", "fp-x", ago=6)
    items = await _events(client, admin_token)
    by_id = {i["id"]: i for i in items}
    assert len(items) == 3
    assert by_id[l2]["occurrences"] == 2
    assert by_id[f1]["occurrences"] == 1

    d = (await client.get(f"/log/events/{l1}", headers=_auth(admin_token))).json()["data"]
    assert d["occurrences"] == 2 and d["recent_ids"] == [l2]
    d = (await client.get(f"/log/events/{f1}", headers=_auth(admin_token))).json()["data"]
    assert d["occurrences"] == 1 and d["recent_ids"] == []


async def test_same_fingerprint_in_other_project_is_separate(client, admin_token, project_with_key):
    pid = project_with_key[2]
    res = await client.post("/project/", headers=_auth(admin_token), json={"name": "second"})
    pid2 = res.json()["data"]["id"]
    await _insert(pid, "x", "fp-shared")
    await _insert(pid2, "x", "fp-shared")
    items = await _events(client, admin_token)
    assert sorted(i["project_id"] for i in items) == sorted([pid, pid2])
    assert all(i["occurrences"] == 1 for i in items)


async def test_ingested_variants_group_and_ignored_groups_still_listed(
    client, admin_token, project_with_key
):
    name, key, _ = project_with_key
    await _ingest(client, name, key, "order 1001 failed")
    await _ingest(client, name, key, "order 2002 failed")
    items = await _events(client, admin_token)
    assert len(items) == 1 and items[0]["occurrences"] == 2
    assert items[0]["message"] == "order 2002 failed"

    async with async_session() as s:
        await s.execute(update(ErrorGroup).values(ignored=True))
        await s.commit()
        assert (await s.execute(select(ErrorGroup.ignored))).scalars().all() == [True]
    items = await _events(client, admin_token)
    assert len(items) == 1 and items[0]["occurrences"] == 2


async def test_filtered_occurrences_within_fingerprint_group(client, admin_token, project_with_key):
    pid = project_with_key[2]
    await _insert(pid, "disk 90% full", "fp-d", ago=120)
    await _insert(pid, "disk 95% full", "fp-d", ago=5)
    since = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    items = await _events(client, admin_token, since=since)
    assert len(items) == 1 and items[0]["occurrences"] == 1

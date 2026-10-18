from datetime import UTC, datetime, timedelta

import pytest
from common.sqlsession import async_session
from routes.logs.model import Errorlog

pytestmark = pytest.mark.asyncio


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _insert(project_id, message="m", errortype="T", level="ERROR",
                  ago_minutes=0, raw=None):
    async with async_session() as s:
        e = Errorlog(
            project_id=project_id,
            errortype=errortype,
            level=level,
            message=message,
            raw=raw,
            timestamp=datetime.now(UTC).replace(tzinfo=None)
            - timedelta(minutes=ago_minutes),
        )
        s.add(e)
        await s.commit()
        await s.refresh(e)
        return e.id


async def test_event_detail_raw_and_group(client, admin_token, project_with_key):
    pid = project_with_key[2]
    ids = [await _insert(pid, "boom", "E", "WARNING" if i != 6 else "ERROR",
                         50 - i * 2, raw=f"raw{i}")
           for i in range(13)]
    await _insert(pid, "other", "E")
    res = await client.get(f"/log/events/{ids[-1]}", headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    d = res.json()["data"]
    assert d["id"] == ids[-1]
    assert d["level"] == "ERROR"
    listed = (await client.get("/log/events", headers=_auth(admin_token))).json()["data"]
    item = next(i for i in listed["items"] if i["message"] == "boom")
    assert {k: d[k] for k in item} == item
    assert d["raw"] == "raw12"
    assert d["occurrences"] == 13
    assert d["first_seen"] < d["last_seen"]
    assert d["recent_ids"] == ids[-2:-12:-1]
    assert len(d["recent_ids"]) == 10 and ids[-1] not in d["recent_ids"]

    # an earlier occurrence: same group, its own raw, excludes itself
    res = await client.get(f"/log/events/{ids[0]}", headers=_auth(admin_token))
    d = res.json()["data"]
    assert d["raw"] == "raw0" and d["occurrences"] == 13
    assert ids[0] not in d["recent_ids"] and d["recent_ids"][0] == ids[-1]


async def test_event_detail_404(client, admin_token):
    res = await client.get("/log/events/9999", headers=_auth(admin_token))
    assert res.status_code == 404


async def test_event_detail_403(client, project_with_key, plain_user):
    eid = await _insert(project_with_key[2], "secret")
    res = await client.get(f"/log/events/{eid}", headers=_auth(plain_user[2]))
    assert res.status_code == 403


async def test_events_list_not_shadowed(client, admin_token, project_with_key):
    eid = await _insert(project_with_key[2], "x")
    res = await client.get("/log/events", headers=_auth(admin_token))
    assert res.status_code == 200 and "items" in res.json()["data"]
    res = await client.get(f"/log/events/{eid}", headers=_auth(admin_token))
    assert res.json()["data"]["id"] == eid

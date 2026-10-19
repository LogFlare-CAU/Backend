from datetime import UTC, datetime, timedelta

import pytest
from common.sqlsession import async_session
from common.timeutil import utc_iso
from routes.logs.model import Errorlog
from sqlalchemy import select

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
    assert [r["id"] for r in d["recent"]] == d["recent_ids"]
    assert all(r["timestamp"] and r["level"] for r in d["recent"])
    assert {r["level"] for r in d["recent"]} <= {"WARNING", "ERROR"}
    assert all(r["message"] is None for r in d["recent"])

    # an earlier occurrence: same group, its own raw, excludes itself
    res = await client.get(f"/log/events/{ids[0]}", headers=_auth(admin_token))
    d = res.json()["data"]
    assert d["raw"] == "raw0" and d["occurrences"] == 13
    assert ids[0] not in d["recent_ids"] and d["recent_ids"][0] == ids[-1]


async def test_event_detail_row_fields_from_requested_row(
    client, admin_token, project_with_key, sample_logfile
):
    pid = project_with_key[2]
    for name in ("a.log", "b.log"):
        r = await client.post(
            f"/project/{pid}/logfile",
            headers=_auth(admin_token),
            json={"name": name, "path": str(sample_logfile)},
        )
        assert r.status_code == 200, r.text
    async with async_session() as s:
        from routes.projects.model import LogFile
        files = {
            f.file_name: f.id
            for f in (await s.execute(select(LogFile))).scalars().all()
        }
    now = datetime.now(UTC).replace(tzinfo=None)
    async with async_session() as s:
        old = Errorlog(project_id=pid, errortype="E", message="grp", level="warning",
                       logfile_id=files["a.log"], timestamp=now - timedelta(hours=2))
        new = Errorlog(project_id=pid, errortype="E", message="grp", level="CRITICAL",
                       logfile_id=files["b.log"], timestamp=now)
        s.add_all([old, new])
        await s.commit()
        await s.refresh(old)
        await s.refresh(new)
        old_id, new_id, old_ts, new_ts = old.id, new.id, old.timestamp, new.timestamp
    d = (await client.get(f"/log/events/{old_id}", headers=_auth(admin_token))).json()["data"]
    assert d["id"] == old_id
    assert d["logfile_id"] == files["a.log"] and d["logfile_name"] == "a.log"
    assert d["row_level"] == "WARNING"
    assert d["occurred_at"] == utc_iso(old_ts)
    assert d["level"] == "CRITICAL"
    assert d["occurrences"] == 2
    assert d["timestamp"] == d["last_seen"] == utc_iso(new_ts)
    d = (await client.get(f"/log/events/{new_id}", headers=_auth(admin_token))).json()["data"]
    assert d["logfile_name"] == "b.log" and d["row_level"] == "CRITICAL"


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


async def test_event_detail_recent_has_row_times_and_differing_message(
    client, admin_token, project_with_key
):
    pid = project_with_key[2]
    a = await _insert(pid, "same", "E", "ERROR", 30)
    b = await _insert(pid, "same", "E", "WARNING", 20)
    res = await client.get(f"/log/events/{b}", headers=_auth(admin_token))
    (r,) = res.json()["data"]["recent"]
    assert r["id"] == a and r["level"] == "ERROR" and r["message"] is None
    with_ts = await client.get(f"/log/events/{a}", headers=_auth(admin_token))
    (r2,) = with_ts.json()["data"]["recent"]
    assert r2["id"] == b and r2["level"] == "WARNING"
    assert r2["timestamp"].endswith("Z") or "+" in r2["timestamp"]

from datetime import UTC, datetime, timedelta

import pytest

from routes.collector import collector
from tests.test_groups_api import _h, seed


@pytest.fixture
def token_file(tmp_path, monkeypatch):
    f = tmp_path / "tok"
    monkeypatch.setenv("LOGFLARE_READ_TOKEN_FILE", str(f))
    return f


@pytest.fixture(autouse=True)
def _state(monkeypatch):
    monkeypatch.setattr(collector, "collector_state", {"ok": False, "last_at": None, "error": None})


async def _events(*rows):
    from common.sqlsession import async_session
    from routes.groups.model import ContainerEvent

    async with async_session() as s:
        for name, ev, at in rows:
            s.add(ContainerEvent(container=name, event=ev, at=at.replace(tzinfo=None), detail=""))
        await s.commit()


@pytest.mark.asyncio
async def test_summary_requires_token(client, token_file):
    token_file.write_text("")
    assert (await client.get("/summary")).status_code == 401
    assert (await client.get("/summary", headers=_h("x"))).status_code == 401
    assert (await client.get("/summary", headers=_h(""))).status_code == 401
    token_file.write_text("secret\n")
    assert (await client.get("/summary", headers=_h("nope"))).status_code == 401
    assert (await client.get("/summary", headers=_h("secret"))).status_code == 200


@pytest.mark.asyncio
async def test_summary_shape(client, token_file):
    token_file.write_text("secret")
    await seed([1, 2, 3, 4, 5, 6, 7], "q")
    from common.sqlsession import async_session
    from routes.groups.model import ErrorGroup
    from sqlalchemy import select
    async with async_session() as s:
        g = (await s.execute(select(ErrorGroup).where(ErrorGroup.count == 7))).scalar_one()
        g.ignored = True
        await s.commit()
    now = datetime.now(UTC)
    await _events(("web", "die", now))
    collector.collector_state.update(ok=True, last_at=now)
    d = (await client.get("/summary", headers=_h("secret"))).json()["data"]
    assert set(d) == {"newGroups24h", "openGroups", "topGroups", "containerEvents24h", "collectorOk", "lastCollectedAt"}
    assert d["newGroups24h"] == 7 and d["openGroups"] == 6
    assert [t["count24h"] for t in d["topGroups"]] == [6, 5, 4, 3, 2]
    assert set(d["topGroups"][0]) == {"container", "message", "count24h", "lastSeen"}
    assert d["topGroups"][0]["container"] == "proj-q"
    assert d["containerEvents24h"][0]["container"] == "web"
    assert d["collectorOk"] is True and isinstance(d["lastCollectedAt"], str)


@pytest.mark.asyncio
async def test_summary_collector_down(client, token_file):
    token_file.write_text("secret")
    collector.collector_state.update(ok=False, last_at=datetime.now(UTC))
    r = await client.get("/summary", headers=_h("secret"))
    assert r.status_code == 200
    assert r.json()["data"]["collectorOk"] is False


@pytest.mark.asyncio
async def test_summary_timestamps_are_utc_aware(client, token_file):
    token_file.write_text("secret")
    await seed([2], "u")
    await _events(("web", "die", datetime.now(UTC)))
    collector.collector_state.update(ok=True, last_at=datetime.now(UTC))
    d = (await client.get("/summary", headers=_h("secret"))).json()["data"]
    for v in (d["topGroups"][0]["lastSeen"], d["containerEvents24h"][0]["at"], d["lastCollectedAt"]):
        assert v.endswith("+00:00"), v


@pytest.mark.asyncio
async def test_summary_events_newest_first(client, token_file):
    token_file.write_text("secret")
    now = datetime.now(UTC)
    await _events(
        ("old", "die", now - timedelta(hours=2)),
        ("new", "die", now),
        ("ancient", "die", now - timedelta(hours=25)),
    )
    d = (await client.get("/summary", headers=_h("secret"))).json()["data"]
    assert [e["container"] for e in d["containerEvents24h"]] == ["new", "old"]


@pytest.mark.asyncio
async def test_summary_message_is_exception_line(client, token_file):
    from common.sqlsession import async_session
    from routes.collector.parse import Entry
    from routes.groups.service import record_entry
    from routes.projects.model import Project

    token_file.write_text("secret")
    tb = "\n".join(["ERROR:    Exception in ASGI application", "Traceback (most recent call last):",
                    '  File "a.py", line 1, in f', "    boom()", "ValueError: bad"])
    async with async_session() as s:
        p = Project(name="api", token=None)
        s.add(p)
        await s.flush()
        await record_entry(s, p.id, "api", Entry("ERROR", "ValueError", tb, datetime.now(UTC)))
        await s.commit()
    d = (await client.get("/summary", headers=_h("secret"))).json()["data"]
    assert d["topGroups"][0]["message"] == "ValueError: bad"

"""record_entry / error_groups tests."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from common.sqlsession import async_session
from routes.collector.parse import Entry
from routes.groups.model import ErrorGroup
from routes.groups.service import record_entry
from routes.logs.model import Errorlog
from routes.projects.model import Project
from tests.test_logs import _ingest


async def _project(session) -> int:
    p = Project(name="p1", token="t1")
    session.add(p)
    await session.commit()
    return p.id


def _entry(msg):
    return Entry("ERROR", "ValueError", msg, datetime.now(UTC))


@pytest.mark.asyncio
async def test_record_entry_groups_and_counts():
    async with async_session() as s:
        pid = await _project(s)
        _, g1, new1 = await record_entry(s, pid, "p1", _entry("failed id 123 at 10.0.0.1"))
        _, g2, new2 = await record_entry(s, pid, "p1", _entry("failed id 456 at 10.0.0.2"))
        await s.commit()
        assert (new1, new2) == (True, False)
        groups = (await s.execute(select(ErrorGroup))).scalars().all()
        assert len(groups) == 1 and groups[0].count == 2
        logs = (await s.execute(select(Errorlog))).scalars().all()
        assert len(logs) == 2 and {x.fingerprint for x in logs} == {groups[0].fingerprint}


@pytest.mark.asyncio
async def test_record_entry_masks_message():
    async with async_session() as s:
        pid = await _project(s)
        log, group, _ = await record_entry(s, pid, "p1", _entry("token=abc"))
        await s.commit()
        assert "abc" not in log.message and "abc" not in group.sample


@pytest.mark.asyncio
async def test_post_log_error_still_204_and_listed(client, admin_token, project_with_key):
    name, token, _ = project_with_key
    await _ingest(client, name, token, "boom")
    res = await client.get("/log/error", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200, res.text
    keys = set(res.json()["data"][0])
    assert {"id", "project_id", "errortype", "message", "level", "timestamp", "fingerprint"} <= keys
    async with async_session() as s:
        assert len((await s.execute(select(ErrorGroup))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_ingest_same_message_twice_over_http(client, project_with_key):
    name, token, _ = project_with_key
    await _ingest(client, name, token, "boom")
    await _ingest(client, name, token, "boom")
    async with async_session() as s:
        groups = (await s.execute(select(ErrorGroup))).scalars().all()
        assert len(groups) == 1 and groups[0].count == 2


@pytest.mark.asyncio
async def test_record_entry_reloaded_group_with_aware_ts():
    async with async_session() as s:
        pid = await _project(s)
        await record_entry(s, pid, "p1", _entry("boom"))
        await s.commit()
    async with async_session() as s:
        _, g, new = await record_entry(s, pid, "p1", _entry("boom"))
        await s.commit()
        assert not new and g.count == 2

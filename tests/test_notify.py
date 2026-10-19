"""알림 규칙: 새 묶음 에러와 컨테이너 장애만 푸시한다."""
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from common.sqlsession import async_session
from routes.fcm.model import FCMToken
from routes.groups.model import ErrorGroup
from routes.logs import tasks
from routes.logs.model import Errorlog
from tests.test_logs import _ingest


@pytest.fixture
def sent(monkeypatch):
    calls = []

    async def fake(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(tasks, "send_fcm_message", fake)
    return calls


async def _event(pid, ev, at, container="web"):
    from routes.groups.model import ContainerEvent

    async with async_session() as s:
        row = ContainerEvent(container=container, event=ev, at=at.replace(tzinfo=None), detail="exit 1", project_id=pid)
        s.add(row)
        await s.commit()
        return row.id


@pytest_asyncio.fixture(autouse=True)
async def superuser_token():
    async with async_session() as s:
        # 레거시(미바인딩) 행 — 최근 등록이어야 전송 대상
        s.add(FCMToken(fcm_token="tok", user_idx=1, last_delivery=datetime.now(UTC)))
        await s.commit()


@pytest.mark.asyncio
async def test_new_group_error_notifies_once(client, project_with_key, sent):
    name, token, _ = project_with_key
    await _ingest(client, name, token, "boom")
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_burst_same_fingerprint_notifies_once(client, project_with_key, sent):
    name, token, _ = project_with_key
    for _ in range(50):
        await _ingest(client, name, token, "same failure")
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_warning_never_notifies(client, project_with_key, sent):
    name, token, _ = project_with_key
    res = await client.post(
        "/log/error",
        headers={"Project": name, "ProjectKey": f"Bearer {token}"},
        json={"errortype": "W", "level": "WARNING", "message": "careful", "test": False},
    )
    assert res.status_code == 204
    assert sent == []


@pytest.mark.asyncio
async def test_ignored_group_never_notifies(client, project_with_key, sent):
    name, token, _ = project_with_key
    await _ingest(client, name, token, "boom")
    sent.clear()
    async with async_session() as s:
        err = (await s.execute(select(Errorlog))).scalars().one()
        group = (await s.execute(select(ErrorGroup))).scalars().one()
        group.ignored = True
        await s.commit()
        await tasks.notify_error(err.id, err.project_id, is_new=True)
    assert sent == []


@pytest.mark.asyncio
async def test_container_event_cooldown(client, project_with_key, sent):
    pid = project_with_key[2]
    t0 = datetime.now(UTC)
    first = await _event(pid, "die", t0)
    assert await tasks.notify_container_event(first) is True
    assert await tasks.notify_container_event(first) is False  # 같은 이벤트 두 번
    assert await tasks.notify_container_event(await _event(pid, "die", t0 + timedelta(minutes=3))) is False
    assert await tasks.notify_container_event(await _event(pid, "die", t0 + timedelta(minutes=11))) is True
    assert await tasks.notify_container_event(await _event(pid, "oom", t0)) is True
    assert len(sent) == 3


@pytest.mark.asyncio
async def test_container_event_failed_send_not_recorded(client, project_with_key, monkeypatch):
    """보내기에 실패하면 쿨다운을 기록하지 않아 다음 이벤트가 막히지 않는다."""
    pid = project_with_key[2]
    t0 = datetime.now(UTC)

    async def boom(*a, **k):
        raise RuntimeError("fcm down")

    monkeypatch.setattr(tasks, "send_fcm_message", boom)
    first = await _event(pid, "die", t0)
    with pytest.raises(RuntimeError):
        await tasks.notify_container_event(first)
    sent = []

    async def ok(*a, **k):
        sent.append(a)

    monkeypatch.setattr(tasks, "send_fcm_message", ok)
    assert await tasks.notify_container_event(await _event(pid, "die", t0 + timedelta(seconds=30))) is True
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_long_message_truncated_in_push(client, project_with_key, sent):
    name, token, _ = project_with_key
    await _ingest(client, name, token, "x" * 10000)
    assert len(sent) == 1
    body, data = sent[0][2], sent[0][3]
    assert len(data["message"]) <= 1000 and len(body) < 1200


@pytest.mark.asyncio
async def test_container_event_timestamp_naive(sent):
    at = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
    async with async_session() as s:
        from routes.projects.model import Project
        s.add(Project(name="web", token=None))
        await s.commit()
        pid = (await s.execute(select(Project.id).where(Project.name == "web"))).scalar_one()
    await tasks.notify_container_event(await _event(pid, "die", at))
    assert sent[0][3]["timestamp"] == "2026-10-18T12:00:00"

import asyncio
import json
import struct
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from common.sqlsession import async_session
from routes.collector import collector
from routes.collector.collector import collect_once, collector_state, purge_old, run_collector
from routes.collector.docker import DockerClient
from routes.groups.model import ErrorGroup
from routes.logs import tasks
from routes.logs.model import Errorlog
from routes.projects.model import Project

NOW = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
TB = [
    "Traceback (most recent call last):",
    '  File "a.py", line 1, in f',
    "    boom()",
    "TossAPIError: failed",
]


def frame(stream: int, text: str) -> bytes:
    data = text.encode()
    return bytes([stream, 0, 0, 0]) + struct.pack(">I", len(data)) + data


def logbody(lines, start=NOW - timedelta(hours=1)):
    return b"".join(
        frame(1, f"{(start + timedelta(seconds=i)).strftime('%Y-%m-%dT%H:%M:%S')}.123456789Z {ln}\n")
        for i, ln in enumerate(lines)
    )


def make_docker(containers, logs=None, events=b"", requests=None, status=200):
    """containers: {name: id}; logs: {name: body bytes}"""
    logs = logs or {}
    by_id = {cid: n for n, cid in containers.items()}

    def handler(req: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(req)
        if status != 200:
            return httpx.Response(status)
        p = req.url.path
        if p == "/containers/json":
            return httpx.Response(200, json=[{"Id": i, "Names": [f"/{n}"]} for n, i in containers.items()])
        if p == "/events":
            return httpx.Response(200, content=events)
        assert not (p.startswith("/containers/") and p.endswith("/json")), "inspect 호출 금지"
        if p.endswith("/logs"):
            return httpx.Response(200, content=logs.get(by_id[p.split("/")[2]], b""))
        return httpx.Response(404)

    return DockerClient("http://docker", transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    async def fake(*a, **k):
        pass

    monkeypatch.setattr(tasks, "send_fcm_message", fake)
    tasks._last_event_push.clear()
    collector.container_events.clear()


async def _count(model):
    async with async_session() as s:
        return len((await s.execute(select(model))).scalars().all())


async def test_logs_demux_and_timestamps():
    body = (
        frame(1, "2026-10-18T01:02:03.123456789Z hello\n")
        + frame(2, "2026-10-18T01:02:04Z oops\n")
    )
    d = make_docker({"a": "id1"}, {"a": body})
    lines = await d.logs("id1", 0)
    assert lines == [
        (datetime(2026, 10, 18, 1, 2, 3, 123456, tzinfo=UTC), "hello"),
        (datetime(2026, 10, 18, 1, 2, 4, tzinfo=UTC), "oops"),
    ]


async def test_collect_creates_container_project_and_groups():
    d = make_docker({"stock-api": "i1"}, {"stock-api": logbody(TB * 3)})
    await collect_once(d, NOW)
    async with async_session() as s:
        projects = (await s.execute(select(Project))).scalars().all()
        groups = (await s.execute(select(ErrorGroup))).scalars().all()
    assert [(p.name, p.token) for p in projects] == [("stock-api", None)]
    assert len(groups) == 1 and groups[0].count == 3


async def test_excluded_containers_skipped():
    body = logbody(["ERROR boom"])
    d = make_docker({"aitg-discordbot": "i1", "logflare": "i2"}, {"aitg-discordbot": body, "logflare": body})
    await collect_once(d, NOW)
    assert await _count(Errorlog) == 0


async def test_restart_does_not_duplicate():
    reqs = []
    d = make_docker({"x": "i1"}, {"x": logbody(["ERROR boom"])}, requests=reqs)
    await collect_once(d, NOW)
    first = await _count(Errorlog)
    await collect_once(d, NOW)
    assert await _count(Errorlog) == first == 1
    since = [float(r.url.params["since"]) for r in reqs if r.url.path.endswith("/logs")]
    first_ts = (NOW - timedelta(hours=1)).timestamp()
    assert since[1] > first_ts + 0.123456


async def test_first_attach_reads_24h():
    reqs = []
    d = make_docker({"x": "i1"}, {"x": logbody(["ERROR boom"])}, requests=reqs)
    await collect_once(d, NOW)
    since = float(next(r for r in reqs if r.url.path.endswith("/logs")).url.params["since"])
    assert abs(since - (NOW - timedelta(hours=24)).timestamp()) < 1


async def test_masked_before_store():
    d = make_docker({"x": "i1"}, {"x": logbody(["ERROR auth failed token=sekret"])})
    await collect_once(d, NOW)
    async with async_session() as s:
        texts = [
            *(await s.execute(select(Errorlog.message))).scalars(),
            *(await s.execute(select(ErrorGroup.sample))).scalars(),
        ]
    assert texts and all("sekret" not in t for t in texts)


async def test_events_notify_die_nonzero_only(monkeypatch):
    calls = []

    async def fake(project_id, container, event, at, detail):
        calls.append((container, event))
        return True

    monkeypatch.setattr(collector, "notify_container_event", fake)

    def ev(action, **attrs):
        return json.dumps(
            {"Action": action, "time": int(NOW.timestamp()) - 5, "Actor": {"Attributes": {"name": "web", **attrs}}}
        ).encode() + b"\n"

    events = (
        ev("die", exitCode="0") + ev("die", exitCode="137")
        + ev("health_status: unhealthy") + ev("health_status: healthy")
    )
    await collect_once(make_docker({}, events=events), NOW)
    assert calls == [("web", "die"), ("web", "unhealthy")]
    assert [e["event"] for e in collector.container_events] == ["die", "unhealthy"]


async def test_docker_error_keeps_loop_alive():
    d = make_docker({}, status=500)
    with pytest.raises(httpx.HTTPStatusError):
        await collect_once(d, NOW)
    state = {"fail": True}

    def handler(req):
        if state["fail"]:
            return httpx.Response(500)
        return httpx.Response(200, json=[]) if req.url.path == "/containers/json" else httpx.Response(200)

    d = DockerClient("http://docker", transport=httpx.MockTransport(handler))
    task = asyncio.create_task(run_collector(d, interval=0.01))
    await asyncio.sleep(0.1)
    assert collector_state["ok"] is False
    state["fail"] = False
    await asyncio.sleep(0.1)
    task.cancel()
    assert collector_state["ok"] is True


async def test_container_project_hidden_token(client, admin_token):
    await collect_once(make_docker({"stock-api": "i1"}, {"stock-api": logbody(["ERROR boom"])}), NOW)
    res = await client.get("/project/", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert "stock-api" in res.text and '"token"' not in res.text


async def test_purge_old_keeps_groups():
    d = make_docker({"x": "i1"}, {"x": logbody(["ERROR boom"], start=NOW - timedelta(days=31))})
    await collect_once(d, NOW - timedelta(days=30))
    async with async_session() as s:
        await purge_old(s, NOW - timedelta(days=30))
        await s.commit()
    assert await _count(Errorlog) == 0
    assert await _count(ErrorGroup) == 1


def _ev(action, age, **attrs):
    return json.dumps(
        {"Action": action, "time": int(NOW.timestamp()) - age, "Actor": {"Attributes": {"name": "web", **attrs}}}
    ).encode() + b"\n"


async def test_old_events_recorded_but_not_pushed(monkeypatch):
    calls = []

    async def fake(project_id, container, event, at, detail):
        calls.append(at)
        return True

    monkeypatch.setattr(collector, "notify_container_event", fake)
    events = _ev("die", 7200, exitCode="1") + _ev("die", 5, exitCode="137")
    await collect_once(make_docker({}, events=events), NOW)
    assert len(collector.container_events) == 2
    assert len(calls) == 1


async def test_container_failure_isolated(monkeypatch):
    calls = []

    async def fake(*a):
        calls.append(a)
        return True

    monkeypatch.setattr(collector, "notify_container_event", fake)

    def handler(req):
        p = req.url.path
        if p == "/containers/json":
            return httpx.Response(200, json=[{"Id": "ia", "Names": ["/a"]}, {"Id": "ib", "Names": ["/b"]}])
        if p == "/events":
            return httpx.Response(200, content=_ev("die", 5, exitCode="1"))
        if p.startswith("/containers/ia"):
            return httpx.Response(404)
        return httpx.Response(200, content=logbody(["ERROR boom"]))

    d = DockerClient("http://docker", transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="a"):
        await collect_once(d, NOW)
    assert await _count(Errorlog) == 1
    assert len(calls) == 1


async def test_notify_failure_still_advances_events_cursor(monkeypatch):
    async def boom(*a):
        raise RuntimeError("push down")

    monkeypatch.setattr(collector, "notify_container_event", boom)
    await collect_once(make_docker({}, events=_ev("die", 5, exitCode="1")), NOW)
    async with async_session() as s:
        cur = await s.get(collector.CollectorCursor, "__events__")
    assert cur.last_ts == NOW.replace(tzinfo=None)
    assert len(collector.container_events) == 1


async def test_logs_raw_tty_and_crlf():
    d = make_docker({"a": "id1"}, {"a": b"2026-10-18T01:02:03Z hi\r\n2026-10-18T01:02:04Z yo\n"})
    lines = await d.logs("id1", 0)
    assert [m for _, m in lines] == ["hi", "yo"]


async def _pushes(monkeypatch, body):
    calls = []

    async def fake(*a, **k):
        calls.append(a)

    monkeypatch.setattr(collector, "notify_error", fake)
    await collect_once(make_docker({"x": "i1"}, {"x": body}), NOW)
    return calls


async def test_backfill_new_group_not_pushed(monkeypatch):
    assert await _pushes(monkeypatch, logbody(["ERROR boom"], start=NOW - timedelta(hours=1))) == []
    assert await _count(ErrorGroup) == 1


async def test_fresh_new_group_pushed(monkeypatch):
    assert len(await _pushes(monkeypatch, logbody(["ERROR boom"], start=NOW - timedelta(seconds=5)))) == 1


async def test_restart_recorded_not_pushed(monkeypatch):
    calls = []

    async def fake(*a):
        calls.append(a)
        return True

    monkeypatch.setattr(collector, "notify_container_event", fake)
    reqs = []
    d = make_docker({}, events=_ev("restart", 5), requests=reqs)
    await collect_once(d, NOW)
    assert calls == []
    assert [e["event"] for e in collector.container_events] == ["restart"]
    ev_req = next(r for r in reqs if r.url.path == "/events")
    assert "restart" in ev_req.url.params["filters"]


async def test_event_for_new_container_pushes_after_project_commit(monkeypatch):
    from routes.fcm.model import FCMToken

    sent = []

    async def fake(*a, **k):
        sent.append(a)

    monkeypatch.setattr(tasks, "send_fcm_message", fake)
    async with async_session() as s:
        s.add(FCMToken(fcm_token="tok", user_idx=1))
        await s.commit()
    await collect_once(make_docker({}, events=_ev("die", 5, exitCode="3", name="brandnew")), NOW)
    assert len(sent) == 1
    async with async_session() as s:
        assert (await s.execute(select(Project).where(Project.name == "brandnew"))).scalar_one()

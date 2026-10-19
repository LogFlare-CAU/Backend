"""send_fcm_message: data-only high-priority message, token pruning, error isolation (no network)."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from firebase_admin import exceptions, messaging
from sqlalchemy import select
from sqlalchemy.sql.dml import Delete

import common.fcm as fcm
from common.sqlsession import async_session
from routes.fcm import service as fcm_service
from routes.fcm.model import FCMToken
from routes.logs import tasks


@pytest.fixture
def fake_send(monkeypatch):
    """Patch messaging.send; `errors` maps token -> exception to raise."""
    state = {"sent": [], "errors": {}}

    def send(message, dry_run=False, app=None):
        state["sent"].append(message)
        err = state["errors"].get(message.token)
        if err is not None:
            raise err
        return f"projects/x/messages/{message.token}"

    monkeypatch.setattr(fcm.messaging, "send", send)
    return state


class _Pruned:
    def __init__(self):
        self.called = 0

    async def __call__(self):
        self.called += 1


@pytest.mark.asyncio
async def test_message_is_data_only_high_priority(fake_send):
    res = await fcm.send_fcm_message("t1", "title", "body", {"k": "v"})
    assert res == "projects/x/messages/t1"
    (msg,) = fake_send["sent"]
    assert msg.notification is None
    assert msg.data == {"k": "v"}
    assert msg.android.priority == "high"
    assert msg.android.ttl == timedelta(hours=24)


@pytest.mark.parametrize(
    "err",
    [
        messaging.UnregisteredError("Requested entity was not found."),
        messaging.SenderIdMismatchError("SenderId mismatch"),
        exceptions.InvalidArgumentError(
            "The registration token is not a valid FCM registration token"
        ),
    ],
    ids=["unregistered", "sender-mismatch", "invalid-token"],
)
@pytest.mark.asyncio
async def test_dead_token_errors_prune(fake_send, err):
    fake_send["errors"]["t1"] = err
    pruned = _Pruned()
    assert await fcm.send_fcm_message("t1", "", "", {}, onfailure=pruned) is None
    assert pruned.called == 1


@pytest.mark.parametrize(
    "err",
    [
        exceptions.InvalidArgumentError("Message payload exceeds 4096 bytes"),
        exceptions.UnavailableError("FCM is down"),
        messaging.QuotaExceededError("quota"),
        ValueError("The default Firebase app does not exist."),
    ],
    ids=["invalid-payload", "unavailable", "quota", "not-initialized"],
)
@pytest.mark.asyncio
async def test_other_errors_logged_not_pruned_not_raised(fake_send, err):
    fake_send["errors"]["t1"] = err
    pruned = _Pruned()
    assert await fcm.send_fcm_message("t1", "", "", {}, onfailure=pruned) is None
    assert pruned.called == 0


@pytest.mark.asyncio
async def test_one_failing_token_does_not_stop_others(client, project_with_key, fake_send):
    now = datetime.now(UTC)
    async with async_session() as s:
        for t in ("a", "dead", "boom", "z"):
            s.add(FCMToken(fcm_token=t, user_idx=1, last_delivery=now))
        await s.commit()
    fake_send["errors"]["dead"] = messaging.UnregisteredError("gone")
    fake_send["errors"]["boom"] = exceptions.InternalError("server error")

    async with async_session() as s:
        await tasks._send_to_recipients(s, project_with_key[2], "t", "m", {"k": "v"})
        await s.commit()

    assert sorted(m.token for m in fake_send["sent"]) == ["a", "boom", "dead", "z"]
    async with async_session() as s:
        left = set((await s.execute(select(FCMToken.fcm_token))).scalars().all())
    assert left == {"a", "boom", "z"}


@pytest.mark.filterwarnings("ignore:New instance:sqlalchemy.exc.SAWarning")
@pytest.mark.asyncio
async def test_prune_commit_failure_does_not_stop_later_recipients(
    client, project_with_key, plain_user, fake_send, monkeypatch
):
    """A failed prune commit must roll back, so later recipients still get theirs."""
    now = datetime.now(UTC)
    async with async_session() as s:
        s.add(FCMToken(fcm_token="dead", user_idx=1, last_delivery=now))
        s.add(FCMToken(fcm_token="z", user_idx=plain_user[3], last_delivery=now))
        await s.commit()
    fake_send["errors"]["dead"] = messaging.UnregisteredError("gone")

    async def fake_project(conn, pid, with_users):
        return SimpleNamespace(users=[SimpleNamespace(user_id=plain_user[3], view=True)])

    monkeypatch.setattr(tasks.project_service, "get_project", fake_project)

    async with async_session() as s:
        real_execute = s.execute
        state = {"failed": False}

        async def flaky_execute(stmt, *a, **kw):
            if not state["failed"] and isinstance(stmt, Delete):
                state["failed"] = True
                # autoflush 실패 -> 세션이 rollback 을 요구하는 상태가 된다
                s.add(FCMToken(idx=1, fcm_token="dup", user_idx=1))
            return await real_execute(stmt, *a, **kw)

        monkeypatch.setattr(s, "execute", flaky_execute)
        await tasks._send_to_recipients(s, project_with_key[2], "t", "m", {})

    assert state["failed"]
    assert sorted(m.token for m in fake_send["sent"]) == ["dead", "z"]


@pytest.mark.asyncio
async def test_prune_skips_row_rebound_after_fetch(client, plain_user):
    now = datetime.now(UTC)
    async with async_session() as s:
        s.add(FCMToken(fcm_token="dev", user_idx=1, last_delivery=now))
        await s.commit()
    async with async_session() as s:
        row = (await s.execute(select(FCMToken))).scalars().one()
        prune = fcm_service.prune_callback(s, row)
        # 전송 중에 다른 사용자가 같은 기기를 다시 등록했다
        async with async_session() as other:
            r = (await other.execute(select(FCMToken))).scalars().one()
            r.user_idx = plain_user[3]
            await other.commit()
        await prune()
    async with async_session() as s:
        (kept,) = (await s.execute(select(FCMToken))).scalars().all()
    assert kept.user_idx == plain_user[3]


@pytest.mark.asyncio
async def test_prune_deletes_unchanged_row(client):
    async with async_session() as s:
        s.add(FCMToken(fcm_token="dev", user_idx=1, last_delivery=datetime.now(UTC)))
        await s.commit()
    async with async_session() as s:
        row = (await s.execute(select(FCMToken))).scalars().one()
        await fcm_service.prune_callback(s, row)()
    async with async_session() as s:
        assert (await s.execute(select(FCMToken))).scalars().all() == []

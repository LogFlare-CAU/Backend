"""send_fcm_message: data-only high-priority message, token pruning, error isolation (no network)."""
from datetime import UTC, datetime, timedelta

import pytest
from firebase_admin import exceptions, messaging
from sqlalchemy import select

import common.fcm as fcm
from common.sqlsession import async_session
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
    assert msg.android.ttl == timedelta(hours=1)


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

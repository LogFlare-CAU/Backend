"""로그인 방식 설정 (LOGFLARE_AUTH_MODES) 과 GET /user/auth/modes."""
from __future__ import annotations

import pytest

from tests.test_access_login import (
    AUD,
    SERVICE,
    TEAM,
    FakeJwkClient,
    _hdr,
    make_jwt,
)

PW = {"username": "admin", "password": "adminpass1"}


@pytest.fixture
def full_access(monkeypatch):
    from common import access

    monkeypatch.setenv("LOGFLARE_ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("LOGFLARE_ACCESS_AUD", AUD)
    monkeypatch.setenv("LOGFLARE_ACCESS_USERS", f"{SERVICE}=admin")
    monkeypatch.setattr(access, "_get_jwk_client", lambda team: FakeJwkClient())


@pytest.fixture(autouse=True)
def clean_modes(monkeypatch):
    from common import access

    access._warned_unknown.clear()
    monkeypatch.delenv("LOGFLARE_AUTH_MODES", raising=False)


async def _modes(client) -> list[str]:
    res = await client.get("/user/auth/modes")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    return body["data"]["modes"]


async def test_default_is_password_only(client, full_access):
    assert await _modes(client) == ["password"]
    assert (await client.post("/user/auth", json=PW)).status_code == 200
    assert (await client.post("/user/auth/access", headers=_hdr(make_jwt()))).status_code == 404


async def test_empty_value_is_default(client, monkeypatch):
    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "  ")
    assert await _modes(client) == ["password"]


async def test_access_only(client, full_access, monkeypatch):
    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "access")
    assert await _modes(client) == ["access"]
    assert (await client.post("/user/auth", json=PW)).status_code == 404
    res = await client.post("/user/auth/access", headers=_hdr(make_jwt()))
    assert res.status_code == 200, res.text


async def test_password_404_uses_envelope_and_skips_rate_limit(client, full_access, monkeypatch):
    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "access")
    for _ in range(8):
        res = await client.post("/user/auth", json={"username": "admin", "password": "wrongpass1"})
        assert res.status_code == 404
    assert res.json()["success"] is False


async def test_both(client, full_access, monkeypatch):
    monkeypatch.setenv("LOGFLARE_AUTH_MODES", " Password , ACCESS ")
    assert await _modes(client) == ["password", "access"]
    assert (await client.post("/user/auth", json=PW)).status_code == 200
    assert (await client.post("/user/auth/access", headers=_hdr(make_jwt()))).status_code == 200


async def test_access_listed_without_config_not_effective(client, monkeypatch):
    for name in ("TEAM_DOMAIN", "AUD", "USERS"):
        monkeypatch.delenv(f"LOGFLARE_ACCESS_{name}", raising=False)
    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "access")
    assert await _modes(client) == []
    assert (await client.post("/user/auth", json=PW)).status_code == 404
    assert (await client.post("/user/auth/access", headers=_hdr(make_jwt()))).status_code == 404

    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "password,access")
    assert await _modes(client) == ["password"]


async def test_unknown_word_ignored_and_logged(client, monkeypatch, caplog):
    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "password,sms")
    with caplog.at_level("WARNING"):
        assert await _modes(client) == ["password"]
    assert "sms" in caplog.text


async def test_unknown_word_warned_once_per_process(client, monkeypatch, caplog):
    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "password,sms")
    with caplog.at_level("WARNING"):
        for _ in range(3):
            await _modes(client)
    assert caplog.text.count("sms") == 1


def test_startup_warns_access_config_without_mode(full_access, monkeypatch, caplog):
    from common.access import warn_auth_mode_mismatch

    with caplog.at_level("WARNING", logger="common.access"):
        warn_auth_mode_mismatch()
    assert "Access 로그인이 꺼져 있습니다" in caplog.text
    assert AUD not in caplog.text and TEAM not in caplog.text


def test_startup_warns_access_mode_without_config(monkeypatch, caplog):
    from common.access import warn_auth_mode_mismatch

    for name in ("TEAM_DOMAIN", "AUD", "USERS"):
        monkeypatch.delenv(f"LOGFLARE_ACCESS_{name}", raising=False)
    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "password,access")
    with caplog.at_level("WARNING", logger="common.access"):
        warn_auth_mode_mismatch()
    assert "Access 설정이 덜 채워져" in caplog.text


def test_startup_quiet_when_consistent(full_access, monkeypatch, caplog):
    from common.access import warn_auth_mode_mismatch

    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "password,access")
    with caplog.at_level("WARNING", logger="common.access"):
        warn_auth_mode_mismatch()
    assert caplog.text == ""


async def test_existing_token_survives_mode_change(client, full_access, monkeypatch):
    token = (await client.post("/user/auth", json=PW)).json()["data"]
    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "access")
    me = await client.get("/user/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


async def test_modes_in_openapi():
    from main import app

    schema = app.openapi()
    op = schema["paths"]["/user/auth/modes"]["get"]
    ref = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert ref, op
    schemas = schema["components"]["schemas"]
    auth_modes = schemas["AuthModes"]
    assert "modes" in auth_modes["properties"]
    assert auth_modes["properties"]["modes"]["type"] == "array"

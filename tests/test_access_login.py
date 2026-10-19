"""Cloudflare Access JWT 로그인 (POST /user/auth/access)."""
from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

TEAM = "team.cloudflareaccess.com"
AUD = "aud-tag-123"
SERVICE = "abc123.access"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _SigningKey:
    def __init__(self, key):
        self.key = key


class FakeJwkClient:
    def get_signing_key_from_jwt(self, token):
        return _SigningKey(_KEY.public_key())


def make_jwt(key=_KEY, **overrides) -> str:
    claims = {
        "aud": [AUD],
        "iss": f"https://{TEAM}",
        "exp": int(time.time()) + 300,
        "common_name": SERVICE,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def access_env(monkeypatch):
    from common import access

    monkeypatch.setenv("LOGFLARE_ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("LOGFLARE_ACCESS_AUD", AUD)
    monkeypatch.setenv("LOGFLARE_ACCESS_USERS", f"{SERVICE}=admin, Me@Example.com=admin")
    monkeypatch.setattr(access, "_get_jwk_client", lambda team: FakeJwkClient())


def _hdr(token):
    return {"Cf-Access-Jwt-Assertion": token}


async def test_unconfigured_is_404(client, monkeypatch):
    for name in ("TEAM_DOMAIN", "AUD", "USERS"):
        monkeypatch.delenv(f"LOGFLARE_ACCESS_{name}", raising=False)
    res = await client.post("/user/auth/access", headers=_hdr(make_jwt()))
    assert res.status_code == 404


async def test_half_configured_is_404_and_app_ok(client, monkeypatch):
    monkeypatch.setenv("LOGFLARE_ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.delenv("LOGFLARE_ACCESS_AUD", raising=False)
    monkeypatch.setenv("LOGFLARE_ACCESS_USERS", f"{SERVICE}=admin")
    res = await client.post("/user/auth/access", headers=_hdr(make_jwt()))
    assert res.status_code == 404
    assert (await client.post("/user/auth", json={"username": "admin", "password": "adminpass1"})).status_code == 200


async def test_service_token_logs_in(client, access_env):
    res = await client.post("/user/auth/access", headers=_hdr(make_jwt()))
    assert res.status_code == 200, res.text
    token = res.json()["data"]
    me = await client.get("/user/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["username"] == "admin"


async def test_email_identity_case_insensitive(client, access_env):
    tok = make_jwt(common_name=None, email="ME@example.COM")
    res = await client.post("/user/auth/access", headers=_hdr(tok))
    assert res.status_code == 200, res.text


async def test_aud_as_string_and_keep_logged_in(client, access_env):
    res = await client.post(
        "/user/auth/access", headers=_hdr(make_jwt(aud=AUD)), json={"keep_logged_in": True}
    )
    assert res.status_code == 200, res.text


@pytest.mark.parametrize(
    "tok",
    [
        make_jwt(key=_OTHER_KEY),
        make_jwt(aud=["other"]),
        make_jwt(iss="https://evil.cloudflareaccess.com"),
        make_jwt(exp=int(time.time()) - 10),
        make_jwt(common_name="unmapped.access"),
        "garbage",
    ],
    ids=["bad-sig", "bad-aud", "bad-iss", "expired", "unmapped", "garbage"],
)
async def test_invalid_is_401(client, access_env, tok):
    res = await client.post("/user/auth/access", headers=_hdr(tok))
    assert res.status_code == 401


async def test_alg_none_is_401(client, access_env):
    tok = jwt.encode(
        {"aud": [AUD], "iss": f"https://{TEAM}", "exp": int(time.time()) + 300, "common_name": SERVICE},
        None,
        algorithm="none",
    )
    res = await client.post("/user/auth/access", headers=_hdr(tok))
    assert res.status_code == 401


async def test_hs256_is_401(client, access_env):
    tok = jwt.encode(
        {"aud": [AUD], "iss": f"https://{TEAM}", "exp": int(time.time()) + 300, "common_name": SERVICE},
        "secret" * 8,
        algorithm="HS256",
    )
    res = await client.post("/user/auth/access", headers=_hdr(tok))
    assert res.status_code == 401


async def test_mapped_user_missing_is_401(client, access_env, monkeypatch):
    monkeypatch.setenv("LOGFLARE_ACCESS_USERS", f"{SERVICE}=nobody")
    res = await client.post("/user/auth/access", headers=_hdr(make_jwt()))
    assert res.status_code == 401


async def test_no_token_is_401(client, access_env):
    res = await client.post("/user/auth/access")
    assert res.status_code == 401


async def test_cookie_fallback(client, access_env):
    client.cookies.set("CF_Authorization", make_jwt())
    res = await client.post("/user/auth/access")
    assert res.status_code == 200, res.text


async def test_repeated_failures_429(client, access_env):
    codes = [
        (await client.post("/user/auth/access", headers=_hdr("garbage"))).status_code for _ in range(7)
    ]
    assert codes[0] == 401
    assert codes[-1] == 429


def test_parse_users():
    from common.access import parse_users

    assert parse_users(" A.access = admin ,Bob@X.com=bob,,bad") == {"a.access": "admin", "bob@x.com": "bob"}

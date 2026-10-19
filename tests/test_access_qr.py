"""관리자용 CF Access 로그인 QR (GET /user/access-qr)."""
from __future__ import annotations

import json
import logging

import pytest

from common.enums import Permissions
from common.sqlsession import async_session
from routes.user import model as user_model
from sqlalchemy import update

TEAM = "team.cloudflareaccess.com"
AUD = "aud-tag-123"
CLIENT_ID = "ad3f0123456789abcdef6e70.access"
SECRET = "s3cr3t-VALUE-0123456789-abcdefghijklmnop"
SERVER = "https://logflare.code0987.me"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def token_file(tmp_path):
    p = tmp_path / "tok.txt"
    p.write_text(
        f"CF-Access-Client-Id: {CLIENT_ID}\nCF-Access-Client-Secret: {SECRET}\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def qr_env(monkeypatch, token_file):
    monkeypatch.setenv("LOGFLARE_PUBLIC_URL", SERVER + "/")
    monkeypatch.setenv("LOGFLARE_ACCESS_QR_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("LOGFLARE_ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("LOGFLARE_ACCESS_AUD", AUD)
    monkeypatch.setenv("LOGFLARE_ACCESS_USERS", f"{CLIENT_ID}=admin")
    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "password,access")


# ---- 단위: 토큰 파일·payload·svg -------------------------------------------

def test_load_qr_token_formats(tmp_path):
    from common.access_qr import load_qr_token

    p = tmp_path / "t.txt"
    p.write_bytes(
        b"\xef\xbb\xbfcf-access-client-id:  abc.access \r\nCF-ACCESS-CLIENT-SECRET: sec \r\n"
    )
    assert load_qr_token(str(p)) == ("abc.access", "sec")
    assert load_qr_token(str(tmp_path / "none.txt")) is None
    assert load_qr_token("") is None
    p.write_text("CF-Access-Client-Id: only\n", encoding="utf-8")
    assert load_qr_token(str(p)) is None
    p.write_text("garbage\n", encoding="utf-8")
    assert load_qr_token(str(p)) is None


def test_qr_payload_exact():
    from common.access_qr import qr_payload

    assert qr_payload("https://x.me", "i.access", "s") == '{"v":1,"server":"https://x.me","id":"i.access","secret":"s"}'


def test_qr_svg_is_svg():
    from common.access_qr import qr_svg

    svg = qr_svg("hello")
    assert svg.startswith("<svg") and "<?xml" not in svg and "#191F28".lower() in svg.lower()


def test_qr_svg_has_svg_namespace():
    """웹 화면이 image/svg+xml 로 파싱하므로 루트에 SVG 네임스페이스가 있어야 한다."""
    import xml.etree.ElementTree as ET

    from common.access_qr import qr_svg

    root = ET.fromstring(qr_svg('{"v":1}'))
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    tags = {el.tag.lower() for el in root.iter()}
    assert not any(t.endswith("script") or t.endswith("foreignobject") for t in tags)


def test_mask_client_id():
    from common.access_qr import mask_client_id

    assert mask_client_id(CLIENT_ID) == "ad3f…6e70"


# ---- API --------------------------------------------------------------------

async def test_admin_gets_qr(client, admin_token, qr_env, monkeypatch):
    import routes.user.application as m

    seen = {}
    real = m.qr_svg

    def spy(payload):
        seen["payload"] = payload
        return real(payload)

    monkeypatch.setattr(m, "qr_svg", spy)
    res = await client.get("/user/access-qr", headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    assert res.headers["cache-control"] == "no-store"
    assert res.headers["pragma"] == "no-cache"
    data = res.json()["data"]
    assert data["svg"].startswith("<svg")
    assert data["server"] == SERVER
    assert data["clientId"] == "ad3f…6e70"
    assert data["mapped"] is True and data["accessEnabled"] is True
    assert json.loads(seen["payload"]) == {"v": 1, "server": SERVER, "id": CLIENT_ID, "secret": SECRET}
    # secret 은 svg 필드 밖 어디에도 없다
    body = res.json()
    body["data"].pop("svg")
    assert SECRET not in json.dumps(body)
    assert SECRET not in "".join(f"{k}:{v}" for k, v in res.headers.items())


async def test_no_secret_in_logs(client, admin_token, qr_env, caplog):
    caplog.set_level(logging.DEBUG)
    res = await client.get("/user/access-qr", headers=_auth(admin_token))
    assert res.status_code == 200
    assert SECRET not in caplog.text
    assert CLIENT_ID not in caplog.text
    assert "access QR viewed by admin" in caplog.text  # 감사 로그: 본 관리자 이름


async def test_unmapped_flags(client, admin_token, qr_env, monkeypatch):
    monkeypatch.setenv("LOGFLARE_ACCESS_USERS", "other.access=admin")
    data = (await client.get("/user/access-qr", headers=_auth(admin_token))).json()["data"]
    assert data["mapped"] is False and data["mappedReason"] == "not_in_map"
    monkeypatch.setenv("LOGFLARE_ACCESS_USERS", f"{CLIENT_ID.upper()}=ghost")
    data = (await client.get("/user/access-qr", headers=_auth(admin_token))).json()["data"]
    assert data["mapped"] is False and data["mappedReason"] == "user_missing"


async def test_access_disabled_flag(client, admin_token, qr_env, monkeypatch):
    monkeypatch.setenv("LOGFLARE_AUTH_MODES", "password")
    data = (await client.get("/user/access-qr", headers=_auth(admin_token))).json()["data"]
    assert data["accessEnabled"] is False


async def test_moderator_forbidden(client, moderator, qr_env):
    res = await client.get("/user/access-qr", headers=_auth(moderator[2]))
    assert res.status_code == 403
    assert SECRET not in res.text


async def test_plain_user_forbidden(client, plain_user, qr_env):
    assert (await client.get("/user/access-qr", headers=_auth(plain_user[2]))).status_code == 403


async def test_demoted_admin_forbidden(client, admin_token, qr_env):
    """JWT 는 admin 시절 발급이지만 DB 에서 강등되면 403."""
    async with async_session() as s:
        await s.execute(update(user_model.User).where(user_model.User.username == "admin").values(permission=Permissions.MODERATOR))
        await s.commit()
    res = await client.get("/user/access-qr", headers=_auth(admin_token))
    assert res.status_code == 403


async def test_invalid_token_401(client, qr_env):
    res = await client.get("/user/access-qr", headers=_auth("not-a-jwt"))
    assert res.status_code == 401


@pytest.mark.parametrize("drop", ["url", "file", "badfile"])
async def test_unconfigured_404(client, admin_token, qr_env, monkeypatch, tmp_path, drop):
    if drop == "url":
        monkeypatch.delenv("LOGFLARE_PUBLIC_URL")
        missing = ["LOGFLARE_PUBLIC_URL"]
    elif drop == "file":
        monkeypatch.delenv("LOGFLARE_ACCESS_QR_TOKEN_FILE")
        missing = ["LOGFLARE_ACCESS_QR_TOKEN_FILE"]
    else:
        bad = tmp_path / "bad.txt"
        bad.write_text("nope", encoding="utf-8")
        monkeypatch.setenv("LOGFLARE_ACCESS_QR_TOKEN_FILE", str(bad))
        missing = ["LOGFLARE_ACCESS_QR_TOKEN_FILE"]
    res = await client.get("/user/access-qr", headers=_auth(admin_token))
    assert res.status_code == 404
    assert res.json()["data"] == {"reason": "qr_unconfigured", "missing": missing}
    assert res.headers["cache-control"] == "no-store"
    # 서버는 정상: 비밀번호 로그인 가능
    assert (await client.post("/user/auth", json={"username": "admin", "password": "adminpass1"})).status_code == 200


@pytest.mark.parametrize("url", ["http://logflare.code0987.me", "logflare.code0987.me", "https://"])
async def test_non_https_public_url_is_unconfigured(client, admin_token, qr_env, monkeypatch, url):
    monkeypatch.setenv("LOGFLARE_PUBLIC_URL", url)
    res = await client.get("/user/access-qr", headers=_auth(admin_token))
    assert res.status_code == 404
    assert res.json()["data"] == {"reason": "qr_unconfigured", "missing": ["LOGFLARE_PUBLIC_URL"]}


async def test_unconfigured_hidden_from_non_admin(client, moderator, monkeypatch):
    monkeypatch.delenv("LOGFLARE_PUBLIC_URL", raising=False)
    res = await client.get("/user/access-qr", headers=_auth(moderator[2]))
    assert res.status_code == 403


async def test_segno_missing_503(client, admin_token, qr_env, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake(name, *a, **k):
        if name == "segno":
            raise ImportError("no segno")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    res = await client.get("/user/access-qr", headers=_auth(admin_token))
    assert res.status_code == 503
    assert res.json()["data"] == {"reason": "qr_lib_missing"}
    assert SECRET not in res.text

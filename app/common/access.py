"""Cloudflare Access JWT 검증 — 서비스 토큰/이메일 신원을 LogFlare 사용자로 매핑하기 위한 도구.

설정(LOGFLARE_ACCESS_TEAM_DOMAIN / _AUD / _USERS)은 요청 시점에 읽는다. 하나라도 비면 기능이 꺼진다.
토큰과 비밀값은 로그에 남기지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from .env_utils import getenvval


class AccessError(Exception):
    """Access JWT 검증 실패 (이유는 호출자에게 구분해 주지 않는다)."""


@dataclass(frozen=True)
class AccessConfig:
    team_domain: str
    aud: str
    users: dict[str, str]


def parse_users(raw: str) -> dict[str, str]:
    """`신원=사용자명` 쉼표 구분 → {소문자 신원: 사용자명}. 형식이 틀린 항목은 건너뛴다."""
    users: dict[str, str] = {}
    for part in (raw or "").split(","):
        identity, sep, username = part.partition("=")
        identity, username = identity.strip().lower(), username.strip()
        if sep and identity and username:
            users[identity] = username
    return users


def load_access_config() -> AccessConfig | None:
    team = str(getenvval("LOGFLARE_ACCESS_TEAM_DOMAIN", "") or "").strip()
    aud = str(getenvval("LOGFLARE_ACCESS_AUD", "") or "").strip()
    users = parse_users(str(getenvval("LOGFLARE_ACCESS_USERS", "") or ""))
    if not team or not aud or not users:
        return None
    return AccessConfig(team_domain=team, aud=aud, users=users)


_jwk_clients: dict[str, PyJWKClient] = {}


def _get_jwk_client(team_domain: str) -> PyJWKClient:
    client = _jwk_clients.get(team_domain)
    if client is None:
        client = PyJWKClient(f"https://{team_domain}/cdn-cgi/access/certs", cache_keys=True)
        _jwk_clients[team_domain] = client
    return client


def verify_access_jwt(token: str, cfg: AccessConfig, jwk_client=None) -> str:
    """서명(RS256)·aud·iss·exp 를 검증하고 신원(email 또는 common_name)을 반환한다."""
    try:
        client = jwk_client or _get_jwk_client(cfg.team_domain)
        key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=cfg.aud,
            issuer=f"https://{cfg.team_domain}",
            options={"require": ["exp", "aud", "iss"]},
        )
    except Exception as exc:  # 서명·클레임·JWKS 조회 실패 모두 같은 실패로
        raise AccessError("invalid access token") from exc
    identity = claims.get("email") or claims.get("common_name")
    if not isinstance(identity, str) or not identity.strip():
        raise AccessError("no identity in access token")
    return identity.strip().lower()

"""Cloudflare Access JWT 검증 — 서비스 토큰/이메일 신원을 LogFlare 사용자로 매핑하기 위한 도구.

설정(LOGFLARE_ACCESS_TEAM_DOMAIN / _AUD / _USERS)은 요청 시점에 읽는다. 하나라도 비면 기능이 꺼진다.
토큰과 비밀값은 로그에 남기지 않는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from .env_utils import getenvval


logger = logging.getLogger(__name__)


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


KNOWN_AUTH_MODES = ("password", "access")


_warned_unknown: set[str] = set()


def _listed_modes() -> tuple[bool, set[str]]:
    """(명시 여부, 목록). 없거나 공백이면 예전 동작: password 항상, access 는 (설정이 있으면) 켬."""
    raw = str(getenvval("LOGFLARE_AUTH_MODES", "") or "").strip()
    if not raw:
        return False, {"password", "access"}
    wanted: set[str] = set()
    for word in raw.split(","):
        word = word.strip().lower()
        if not word:
            continue
        if word in KNOWN_AUTH_MODES:
            wanted.add(word)
        elif word not in _warned_unknown:
            _warned_unknown.add(word)
            logger.warning("LOGFLARE_AUTH_MODES: unknown mode ignored: %s", word)
    return True, wanted


def warn_auth_mode_mismatch() -> None:
    """시작 시 한 번: 명시한 LOGFLARE_AUTH_MODES 가 Access 설정과 어긋나거나 쓸 수 있는 방식이 없으면 알린다."""
    explicit, listed = _listed_modes()
    if not explicit:
        return
    if not listed:
        logger.error(
            "LOGFLARE_AUTH_MODES 에 쓸 수 있는 로그인 방식이 없습니다 (password, access 중에서 고르세요). "
            "새 로그인이 모두 막힙니다"
        )
        return
    configured = load_access_config() is not None
    if configured and "access" not in listed:
        logger.warning(
            "Access 설정은 있으나 LOGFLARE_AUTH_MODES 에 access 가 없어 Access 로그인이 꺼져 있습니다 "
            "(켜려면 LOGFLARE_AUTH_MODES=password,access)"
        )
    elif not configured and "access" in listed:
        logger.warning("LOGFLARE_AUTH_MODES 에 access 가 있으나 Access 설정이 덜 채워져 꺼져 있습니다")


def effective_auth_modes() -> list[str]:
    """LOGFLARE_AUTH_MODES 중 실제로 켜진 로그인 방식 (["password","access"] 순서). 요청 시점에 읽는다.

    미설정/공백이면 예전 동작(password 항상, Access 설정이 있으면 access 도). 명시하면 그 목록만.
    access 는 Access 설정 세 가지가 모두 있을 때만 유효하다.
    """
    explicit, wanted = _listed_modes()
    if "access" in wanted and load_access_config() is None:
        if explicit:
            logger.debug("LOGFLARE_AUTH_MODES lists access but Access settings are incomplete")
        wanted.discard("access")
    return [m for m in KNOWN_AUTH_MODES if m in wanted]


_jwk_clients: dict[str, PyJWKClient] = {}


def _get_jwk_client(team_domain: str) -> PyJWKClient:
    client = _jwk_clients.get(team_domain)
    if client is None:
        client = PyJWKClient(f"https://{team_domain}/cdn-cgi/access/certs", cache_keys=True, timeout=5)
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
            leeway=30,
            options={"require": ["exp", "aud", "iss"]},
        )
    except Exception as exc:  # 서명·클레임·JWKS 조회 실패 모두 같은 실패로
        logger.warning("Access JWT verification failed: %s", type(exc).__name__)
        raise AccessError("invalid access token") from exc
    identity = claims.get("email") or claims.get("common_name")
    if not isinstance(identity, str) or not identity.strip():
        raise AccessError("no identity in access token")
    return identity.strip().lower()

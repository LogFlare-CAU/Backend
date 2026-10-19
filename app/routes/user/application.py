from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_404_NOT_FOUND

from common.access import AccessError, effective_auth_modes, load_access_config, parse_users, verify_access_jwt
from common.access_qr import QrLibMissing, load_qr_token, mask_client_id, qr_payload, qr_svg
from common.env_utils import getenvval
from common.logger_setup import get_logger
from common.schema import APIResponse, ErrorResponse
from common.client_ip import get_client_ip
from common.rate_limit import check_login_rate_limit, reset_login_rate_limit
from common.security import hash_password, verify_password

from . import schema, service

logger = get_logger()
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

# Verified against when the username doesn't exist, so an unknown user costs the
# same hashing time as a wrong password and the two can't be told apart.
_DUMMY_HASH = hash_password("logflare-unknown-user")


async def authenticate_user(conn: AsyncSession, items: schema.UserAuthParams, client_ip: str) -> str:
    if "password" not in effective_auth_modes():
        raise HTTPException(HTTP_404_NOT_FOUND)
    rate_limit_key = f"{client_ip}:{items.username}"
    check_login_rate_limit(rate_limit_key)
    try:
        user = await service.get_user(conn, items.username)
    except HTTPException:
        verify_password(_DUMMY_HASH, items.password)
        raise HTTPException(HTTP_401_UNAUTHORIZED) from None
    if not verify_password(user.password, items.password):
        raise HTTPException(HTTP_401_UNAUTHORIZED)
    reset_login_rate_limit(rate_limit_key)
    token = await service.create_token(conn, user.idx, items.keep_logged_in)
    return token.token


async def authenticate_access(conn: AsyncSession, request: Request, keep_logged_in: bool) -> str:
    """Cloudflare Access JWT 로 로그인. 설정이 없으면 404, 그 외 실패는 모두 401."""
    cfg = load_access_config()
    if cfg is None or "access" not in effective_auth_modes():
        raise HTTPException(HTTP_404_NOT_FOUND)
    rate_limit_key = f"access:{get_client_ip(request)}"
    check_login_rate_limit(rate_limit_key)
    token = request.headers.get("Cf-Access-Jwt-Assertion") or request.cookies.get("CF_Authorization")
    if not token:
        raise HTTPException(HTTP_401_UNAUTHORIZED)
    try:
        # JWKS 조회는 블로킹 urllib 이라 이벤트 루프 밖에서
        identity = await run_in_threadpool(verify_access_jwt, token, cfg)
    except AccessError:
        raise HTTPException(HTTP_401_UNAUTHORIZED) from None
    username = cfg.users.get(identity)
    if not username:
        raise HTTPException(HTTP_401_UNAUTHORIZED)
    try:
        user = await service.get_user(conn, username)
    except HTTPException:
        raise HTTPException(HTTP_401_UNAUTHORIZED) from None
    reset_login_rate_limit(rate_limit_key)
    created = await service.create_token(conn, user.idx, keep_logged_in)
    return created.token


def _qr_response(status_code: int, message: str, data: dict) -> JSONResponse:
    """QR 관련 에러는 no-store 헤더를 붙여 직접 만든다 (전역 핸들러는 헤더를 버린다)."""
    body = ErrorResponse(success=False, message=message, error_code=status_code, data=data)
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"), headers=NO_STORE)


async def build_access_qr(conn: AsyncSession, admin_username: str) -> JSONResponse:
    """관리자용 Access 로그인 QR. secret 은 SVG 안에만 넣고 로그·예외에는 남기지 않는다."""
    server = str(getenvval("LOGFLARE_PUBLIC_URL", "") or "").strip().rstrip("/")
    token_file = str(getenvval("LOGFLARE_ACCESS_QR_TOKEN_FILE", "") or "").strip()
    token = load_qr_token(token_file)
    missing = []
    if not server.lower().startswith("https://") or len(server) <= len("https://"):
        missing.append("LOGFLARE_PUBLIC_URL")
    if token is None:
        missing.append("LOGFLARE_ACCESS_QR_TOKEN_FILE")
    if missing or token is None:
        return _qr_response(HTTP_404_NOT_FOUND, "QR is not configured", {"reason": "qr_unconfigured", "missing": missing})
    client_id, secret = token
    try:
        svg = qr_svg(qr_payload(server, client_id, secret))
    except QrLibMissing:
        return _qr_response(503, "QR library missing", {"reason": "qr_lib_missing"})

    cfg = load_access_config()
    username = (cfg.users if cfg else parse_users(str(getenvval("LOGFLARE_ACCESS_USERS", "") or ""))).get(client_id.lower())
    mapped, reason = False, None
    if not username:
        reason = "not_in_map"
    else:
        try:
            await service.get_user(conn, username)
            mapped = True
        except HTTPException:
            reason = "user_missing"
    data = {
        "svg": svg,
        "server": server,
        "clientId": mask_client_id(client_id),
        "mapped": mapped,
        "accessEnabled": "access" in effective_auth_modes(),
    }
    if reason:
        data["mappedReason"] = reason
    logger.info("access QR viewed by %s", admin_username)
    return JSONResponse(content=APIResponse(data=data).model_dump(mode="json"), headers=NO_STORE)

from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.status import HTTP_403_FORBIDDEN
from common.enums import Permissions
from common.jwt_utils import decode_jwt

bearer_scheme = HTTPBearer(auto_error=False)

async def _require_moderator(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
):
    if credentials is None:
        raise HTTPException(HTTP_403_FORBIDDEN, "Authorization token is missing")
    try:
        payload = decode_jwt(credentials.credentials)
        if int(payload.get("perm", 0)) < Permissions.MODERATOR:
            raise HTTPException(HTTP_403_FORBIDDEN, "Insufficient permissions")
    except Exception as e:
        raise HTTPException(HTTP_403_FORBIDDEN, "Invalid token") from e
    return payload  # 필요하면 request.state에 붙여도 됨

require_moderator = [Depends(_require_moderator)]
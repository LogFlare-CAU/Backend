from typing import Sequence

from pydantic import BaseModel, Field, field_validator

from common.enums import Permissions
from common.schema import make_named_response

from .model import User


class UserAuthParams(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, description="사용자명")
    password: str = Field(..., min_length=8, description="사용자 비밀번호")
    keep_logged_in: bool = Field(False, description="로그인 상태 유지 여부")


class UserCreateParams(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, description="사용자명")
    password: str = Field(..., min_length=8, description="사용자 비밀번호")
    permission: int = Field(Permissions.USER, description="사용자 권한")

    @field_validator("permission")
    @classmethod
    def permission_valid(cls, v: int) -> int:
        if v < Permissions.USER:
            raise ValueError("Invalid permission value")
        return v


class ResetPasswordParams(BaseModel):
    new_password: str = Field(..., min_length=8, description="새 비밀번호")


class LogoutParams(BaseModel):
    fcm_token: str | None = Field(
        None, description="이 기기의 FCM 토큰 (옵션). 본인 소유면 함께 삭제합니다."
    )


class LogoutResult(BaseModel):
    logged_out: bool = Field(..., description="현재 로그인 토큰 삭제 여부 (항상 true)")
    fcm_removed: bool = Field(..., description="body 의 fcm_token 행을 삭제했는지 여부")


class UserUpdateParams(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=32, description="사용자명")
    permission: int | None = Field(None, description="사용자 권한")
    password: str | None = Field(None, min_length=8, description="사용자 비밀번호")

    @field_validator("permission")
    @classmethod
    def permission_valid(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v < Permissions.USER:
            raise ValueError("Invalid permission value")
        return v


UserResponse = make_named_response(User, "UserResponse")
UserSequenceResponse = make_named_response(Sequence[User], "UserSequenceResponse")


class AuthModes(BaseModel):
    modes: list[str] = Field(..., description='서버가 허용하는 로그인 방식 ("password", "access" 순서)')


class AccessQr(BaseModel):
    svg: str = Field(..., description="앱 로그인용 QR (SVG 문자열). 앱 전용 서비스 토큰 secret 은 여기에만 담긴다")
    server: str = Field(..., description="LogFlare 공개 주소")
    clientId: str = Field(..., description="서비스 토큰 client ID 앞 4·뒤 4 글자")
    mapped: bool = Field(..., description="이 client ID 가 LOGFLARE_ACCESS_USERS 에 있고 그 사용자가 DB 에 있는가")
    mappedReason: str | None = Field(None, description='mapped 가 false 일 때: "not_in_map" | "user_missing"')
    accessEnabled: bool = Field(..., description="Access 로그인이 켜져 있는가")


class AccessAuthParams(BaseModel):
    keep_logged_in: bool = Field(False, description="로그인 상태 유지 여부")

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
    def permission_below_admin(cls, v: int) -> int:
        if v >= Permissions.ADMINISTRATOR:
            raise ValueError("Cannot assign administrator permission via API")
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
    def permission_below_admin(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v >= Permissions.ADMINISTRATOR:
            raise ValueError("Cannot assign administrator permission via API")
        if v < Permissions.USER:
            raise ValueError("Invalid permission value")
        return v


UserResponse = make_named_response(User, "UserResponse")
UserSequenceResponse = make_named_response(Sequence[User], "UserSequenceResponse")

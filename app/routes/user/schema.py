from pydantic import BaseModel, Field

from common.schema import make_named_response
from common.enums import Permissions
from .model import User


class UserAuthParams(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, description="사용자명")
    password: str = Field(..., min_length=8, description="사용자 비밀번호")
    keep_logged_in: bool = Field(False, description="로그인 상태 유지 여부")


class UserCreateParams(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, description="사용자명")
    password: str = Field("password", min_length=8, description="사용자 비밀번호")
    permission: int = Field(Permissions.USER, description="사용자 권한")


UserResponse = make_named_response(User, "UserResponse")

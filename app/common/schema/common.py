from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """
    API 공통 응답 스키마
    """
    success: bool = Field(True, description="API 호출 성공 여부")
    message: str = Field("success", description="처리 결과에 대한 메시지")
    error_code: Optional[int] = Field(None, description="에러 코드")
    data: Optional[T] = Field(None, description="API 호출 결과 데이터")


class ErrorResponse(APIResponse[Any]):
    """
    API 에러 응답 스키마
    """
    success: bool = Field(False, description="API 호출 성공 여부")
    message: str = Field("error", description="에러 메시지")
    error_code: int = Field(..., description="에러 코드")
    data: Optional[Any] = Field(None, description="에러 상세 메시지")
    model_config = ConfigDict(title="ErrorResponse")


def response_maker(include: list[int] = None) -> dict[int, dict]:
    """
    Swagger/OpenAPI responses 블록을 자동 생성.
    - include: 지정된 상태 코드만 포함
    """
    default_errors: dict[int, str] = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Validation Error",
        429: "Too Many Requests",
        500: "Server Error",
    }
    if include is None:
        include = set()
    else:
        include = set(include)
    returnval = {
        code: {
            "model": ErrorResponse,
            "description": default_errors[code],
        }
        for code in sorted(include)
    }
    return returnval


IntegerResponse = APIResponse[int]
IntegerResponse.__name__ = "IntegerResponse"

StringResponse = APIResponse[str]
StringResponse.__name__ = "StringResponse"

StringSequenceResponse = APIResponse[list[str]]
StringSequenceResponse.__name__ = "StringSequenceResponse"

BooleanResponse = APIResponse[bool]
BooleanResponse.__name__ = "BooleanResponse"

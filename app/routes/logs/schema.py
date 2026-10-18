from typing import Sequence

from pydantic import BaseModel, Field

from common.schema import make_named_response

from . import model


class ErrorParams(BaseModel):
    errortype: str | None = Field(None, description="에러 타입")
    level: str = Field(..., description="로그 레벨")
    message: str = Field(..., description="에러 메시지")
    logfile: str | None = Field(None, description="프로젝트 내 로그 파일 이름")
    raw: str | None = Field(None, description="원본 로그 페이로드 (64KB 초과 시 잘림)")
    test: bool = Field(False, description="테스트용 플래그")


ErrorResponse = make_named_response(model.Errorlog, "ErrorResponse")
ErrorSequenceResponse = make_named_response(
    Sequence[model.Errorlog], "ErrorSequenceResponse"
)

from typing import Sequence

from common.schema import make_named_response
from pydantic import BaseModel, Field
from . import model


class ErrorParams(BaseModel):
    project: str = Field(..., description="프로젝트 명")
    level: str = Field(..., description="로그 레벨")
    errortype: str = Field(..., description="에러 타입")
    message: str = Field(..., description="에러 메시지")


ErrorResponse = make_named_response(model.Errorlog, "ErrorResponse")
ErrorSequenceResponse = make_named_response(
    Sequence[model.Errorlog], "ErrorSequenceResponse"
)

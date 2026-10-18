from datetime import datetime
from typing import Sequence

from pydantic import BaseModel, Field

from common.schema import APIResponse, make_named_response

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


class ProjectSummary(BaseModel):
    project_id: int
    error_count: int = Field(..., description="윈도우 내 ERROR+CRITICAL 수")
    warning_count: int = Field(..., description="윈도우 내 WARNING 수")
    last_error_at: datetime | None = Field(
        None, description="가장 최근 ERROR/CRITICAL 시각 (전체 기간, UTC)"
    )


class LogSummary(BaseModel):
    window_hours: int
    since: datetime
    counts: dict[str, int]
    projects: list[ProjectSummary]


class LogSummaryResponse(APIResponse[LogSummary]):
    pass


class LogEvent(BaseModel):
    id: int = Field(..., description="그룹의 최신 에러 ID (grouped=false 면 행 ID)")
    project_id: int
    logfile_id: int | None = None
    logfile_name: str | None = None
    errortype: str | None = None
    message: str
    level: str = Field(..., description="그룹 내 최고 레벨")
    timestamp: datetime = Field(..., description="last_seen 과 동일")
    occurrences: int
    first_seen: datetime
    last_seen: datetime


class LogEventDetail(LogEvent):
    occurred_at: datetime = Field(..., description="요청한 행의 발생 시각")
    row_level: str = Field(..., description="요청한 행의 레벨 (대문자)")
    raw: str | None = Field(None, description="이 에러의 원본 로그 페이로드")
    recent_ids: list[int] = Field(
        default_factory=list, description="같은 그룹의 최신 ID 최대 10개 (자신 제외, 최신순)"
    )


class LogEventDetailResponse(APIResponse[LogEventDetail]):
    pass


class LogEventPage(BaseModel):
    items: list[LogEvent]
    next_cursor: str | None = None


class LogEventPageResponse(APIResponse[LogEventPage]):
    pass

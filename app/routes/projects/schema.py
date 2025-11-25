from typing import Sequence

from common.schema import make_named_response
from . import model
from pydantic import BaseModel, Field


class ProjectCreateParams(BaseModel):
    name: str = Field(..., description="프로젝트 명")


class LogFileCreateParams(BaseModel):
    name: str = Field(..., description="파일 명 (저장하고 픈 이름)")
    path: str = Field(..., description="파일 절대 경로")


class ProjectPermsParams(BaseModel):
    userid: int = Field(..., description="유저 ID")
    projectid: int = Field(..., description="프로젝트 ID")


ProjectResponse = make_named_response(model.Project, "ProjectResponse")
ProjectSequenceResponse = make_named_response(
    Sequence[model.Project], "ProjectSequenceResponse"
)
LogFileResponse = make_named_response(model.LogFile, "LogFileResponse")
ProjectPermsResponse = make_named_response(model.ProjectPerms, "ProjectPermsResponse")

from common.schema import make_named_response
from . import model
from pydantic import BaseModel, Field


class ProjectCreateParams(BaseModel):
    name: str = Field(..., description="프로젝트 명")


class LogFileCreateParams(BaseModel):
    name: str = Field(..., description="파일 명 (저장하고 픈 이름)")
    path: str = Field(..., description="파일 절대 경로")


ProjectResponse = make_named_response(model.Project, "ProjectResponse")

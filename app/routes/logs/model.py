from datetime import datetime, UTC

from common.basemodel import Base
from sqlalchemy import Integer, Text, DateTime, Column, ForeignKey
from sqlalchemy.orm import relationship
from routes.projects.model import Project


class Errorlog(Base):
    __tablename__ = "errorlog"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    project_id = Column(
        Integer,
        ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        comment="Project ID",
    )
    errortype = Column(Text, nullable=False, comment="에러 타입")
    message = Column(Text, nullable=False, comment="에러 메시지 본문")
    level = Column(Text, nullable=False, comment="에러 레벨 (WARNING, ERROR 등)")
    timestamp = Column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC), comment="Timestamp"
    )

    # 단방향 관계: Errorlog.project 로만 접근. Project 쪽에는 컬렉션/역참조 없음.
    project = relationship(
        "Project",
        lazy="selectin",
        passive_deletes=True,  # 부모(Project) 삭제 시 FK ondelete를 신뢰(사전 로드/DELETE 없이)
    )

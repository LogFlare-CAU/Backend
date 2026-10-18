from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import relationship

from common.basemodel import Base


class Errorlog(Base):
    __tablename__ = "errorlogs"
    __table_args__ = (
        Index("ix_errorlogs_project_ts", "project_id", "timestamp"),
        Index("ix_errorlogs_level", "level"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="Project ID",
    )
    errortype = Column(
        Text,
        nullable=True,
        comment="에러 타입, 예: ValidationError, 근데 일부 라이브러리의 경우 없음",
    )
    message = Column(Text, nullable=False, comment="에러 메시지 본문")
    level = Column(Text, nullable=False, comment="에러 레벨 (WARNING, ERROR 등)")
    timestamp = Column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC), comment="Timestamp"
    )
    logfile_id = Column(
        Integer,
        ForeignKey("log_files.id", ondelete="SET NULL"),
        nullable=True,
        comment="연결된 로그 파일 ID (없으면 NULL)",
    )
    raw = Column(Text, nullable=True, comment="원본 로그 페이로드 (최대 64KB)")

    fingerprint = Column(Text, nullable=True, index=True, comment="묶음 지문")

    # 단방향 관계: Errorlog.project 로만 접근. Project 쪽에는 컬렉션/역참조 없음.
    project = relationship(
        "Project",
        lazy="selectin",
        passive_deletes=True,  # 부모(Project) 삭제 시 FK ondelete를 신뢰(사전 로드/DELETE 없이)
    )
    logfile = relationship(
        "LogFile",
        lazy="selectin",
        passive_deletes=True,  # LogFile 삭제 시 FK ondelete=SET NULL 을 신뢰
    )

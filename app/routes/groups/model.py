from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text

from common.basemodel import Base


class ErrorGroup(Base):
    __tablename__ = "error_groups"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    fingerprint = Column(Text, nullable=False, unique=True, comment="묶음 지문")
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="Project ID",
    )
    level = Column(Text, nullable=False, comment="에러 레벨")
    errortype = Column(Text, nullable=True, comment="에러 타입")
    sample = Column(Text, nullable=False, comment="대표 메시지(처음 것)")
    first_seen = Column(DateTime, nullable=False, comment="처음 본 시각")
    last_seen = Column(DateTime, nullable=False, comment="마지막으로 본 시각")
    count = Column(Integer, nullable=False, default=1, comment="발생 횟수")
    ignored = Column(Boolean, nullable=False, default=False, comment="무시 여부")


class CollectorCursor(Base):
    __tablename__ = "collector_cursors"

    container = Column(Text, primary_key=True, comment="컨테이너 이름 (이벤트는 __events__)")
    last_ts = Column(DateTime, nullable=False, comment="마지막으로 읽은 시각")

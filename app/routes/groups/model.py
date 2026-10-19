from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint

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
    pending = Column(
        Text, nullable=True, comment="아직 끝나지 않은 줄 JSON [[iso 시각, 줄], ...] — 다음 폴링에 이어 붙인다"
    )


class ContainerEvent(Base):
    __tablename__ = "container_events"
    __table_args__ = (UniqueConstraint("container", "event", "at", name="uq_container_events_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    container = Column(Text, nullable=False, comment="컨테이너 이름")
    event = Column(Text, nullable=False, comment="die / oom / unhealthy / restart")
    at = Column(DateTime, nullable=False, index=True, comment="이벤트 시각 (naive UTC)")
    detail = Column(Text, nullable=False, default="", comment="설명")
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, comment="Project ID"
    )
    pushed_at = Column(DateTime, nullable=True, comment="푸시를 보낸 시각 (쿨다운 판단)")

from sqlalchemy import Column, Integer, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from common.basemodel import Base


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    name = Column(Text, nullable=False, unique=True, comment="프로젝트 이름")
    alias = Column(
        Text, nullable=True, comment="프로젝트 별칭, 사용할지는 모르겠습니다"
    )
    description = Column(
        Text, nullable=True, comment="프로젝트 설명, 이것도 사용할지는 모르겠습니다"
    )
    token = Column(Text, nullable=True, unique=True, comment="프로젝트 토큰")
    logfiles = relationship(
        "LogFile",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,  # SQLite일 때 ondelete 동작에 도움
        lazy="selectin",
    )


class LogFile(Base):
    __tablename__ = "log_files"
    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),  # ← 테이블명 단수→복수로 수정
        nullable=False,
        comment="프로젝트 ID",
    )
    file_path = Column(Text, nullable=False, comment="로그 파일 경로")
    file_name = Column(Text, nullable=False, comment="로그 파일 이름")
    project = relationship(
        "Project",
        back_populates="logfiles",
        lazy="selectin",
    )


class ProjectPerms(Base):
    __tablename__ = "project_perms"
    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="프로젝트 ID",
    )
    user_id = Column(
        Integer,
        ForeignKey("users.idx", ondelete="CASCADE"),
        nullable=False,
        comment="유저 ID",
    )
    view = Column(Boolean, nullable=False, default=0, comment="뷰 권한")

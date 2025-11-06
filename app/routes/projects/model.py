from sqlalchemy import Column, Integer, Text, ForeignKey
from sqlalchemy.orm import relationship

from common.basemodel import Base


class Project(Base):
    __tablename__ = "project"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    name = Column(Text, nullable=False, unique=True, comment="프로젝트 이름")
    alias = Column(
        Text, nullable=True, comment="프로젝트 별칭, 사용할지는 모르겠습니다"
    )
    description = Column(
        Text, nullable=True, comment="프로젝트 설명, 이것도 사용할지는 모르겠습니다"
    )
    token = Column(Text, nullable=False, unique=True, comment="프로젝트 토큰")
    logfiles = relationship(
        "LogFile", back_populates="project", cascade="all, delete-orphan"
    )


class LogFile(Base):
    __tablename__ = "log_files"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    project_id = Column(
        Integer,
        ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        comment="프로젝트 ID",
    )
    file_path = Column(Text, nullable=False, comment="로그 파일 경로")
    file_name = Column(Text, nullable=False, comment="로그 파일 이름")
    project = relationship("Project", back_populates="logfiles")

from common.basemodel import Base
from sqlalchemy import Column, Integer, String


class User(Base):
    __tablename__ = 'user'
    idx = Column(Integer, primary_key=True, autoincrement=True)
    userid = Column(String(32), nullable=False, comment="사용자 ID")
    password = Column(String(128), nullable=False, comment="사용자 비밀번호, 난수처리")
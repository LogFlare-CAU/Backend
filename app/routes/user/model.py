from common.basemodel import Base
from sqlalchemy import Column, Integer, String, ForeignKey, Text


class User(Base):
    __tablename__ = "users"
    idx = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(32), nullable=False, comment="사용자 ID", unique=True)
    password = Column(
        String(128), nullable=False, comment="사용자 비밀번호, argon2 암호화"
    )
    permission = Column(
        Integer,
        nullable=False,
        default=0,
        comment="사용자 권한, 아직 어떻게 쓸지 몰라서 0으로 초기화",
    )


class Token(Base):
    __tablename__ = "tokens"
    idx = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(Text, nullable=False, comment="인증 토큰")
    user_idx = Column(
        Integer,
        ForeignKey("users.idx", ondelete="CASCADE"),
        nullable=False,
        comment="사용자 고유번호",
    )
    exp = Column(Integer, nullable=False, comment="토큰 만료 시간(UNIX TIMESTAMP)")

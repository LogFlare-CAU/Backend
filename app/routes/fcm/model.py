from common.basemodel import Base
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text


class FCMToken(Base):
    __tablename__ = "fcm_tokens"
    idx = Column(Integer, primary_key=True, autoincrement=True)
    fcm_token = Column(Text, nullable=False, unique=True, comment="FCM 토큰")
    last_delivery = Column(
        DateTime, nullable=True, comment="마지막 푸시 알림 전송 시간"
    )
    user_idx = Column(
        Integer,
        ForeignKey("users.idx", ondelete="CASCADE"),
        nullable=False,
        comment="사용자 고유번호",
    )

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text

from common.basemodel import Base


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
    # 등록한 로그인 토큰. NULL 이면 바인딩 이전(레거시) 행 — last_delivery 기준 30일 뒤 정리.
    token_idx = Column(
        Integer,
        ForeignKey(
            "tokens.idx", ondelete="CASCADE", name="fk_fcm_tokens_token_idx_tokens"
        ),
        nullable=True,
        index=True,
        comment="등록한 로그인 토큰 고유번호",
    )

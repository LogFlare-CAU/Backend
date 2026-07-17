from typing import Optional

from pydantic import BaseModel, Field

from common.schema import make_named_response

from .model import FCMToken


class FCMClientConfig(BaseModel):
    """Minimal Firebase client fields needed by the mobile app."""

    project_id: Optional[str] = None
    messaging_sender_id: Optional[str] = None
    mobilesdk_app_id: Optional[str] = None
    package_name: Optional[str] = None
    api_key: Optional[str] = None


class FCMTestParams(BaseModel):
    title: str = Field(..., description="알림 제목")
    body: str = Field(..., description="알림 내용")
    data: dict[str, str] = Field(default_factory=dict, description="추가 데이터 페이로드 (옵션)")


class FCMTokenParams(BaseModel):
    fcm_token: str = Field(..., description="FCM 토큰")


FCMTokenResponse = make_named_response(FCMToken, "FCMTokenResponse")

from typing import List
from pydantic import BaseModel, Field
from common.schema import make_named_response, APIResponse
from .model import FCMToken


# ==============================================================
# FCM Configuration Schema
# ==============================================================
class _AndroidClientInfo(BaseModel):
    package_name: str


class _ClientInfo(BaseModel):
    mobilesdk_app_id: str
    android_client_info: _AndroidClientInfo


class _ApiKey(BaseModel):
    current_key: str


class _AppInviteService(BaseModel):
    other_platform_oauth_client: List[dict]


class _Services(BaseModel):
    appinvite_service: _AppInviteService


class _Client(BaseModel):
    client_info: _ClientInfo
    oauth_client: List[dict]
    api_key: List[_ApiKey]
    services: _Services


class _ProjectInfo(BaseModel):
    project_number: str
    project_id: str
    storage_bucket: str


class FCMConfig(BaseModel):
    # 이거 쓰시면 됩니다.
    project_info: _ProjectInfo
    client: List[_Client]
    configuration_version: str


# ==============================================================


class FCMTestParams(BaseModel):
    title: str = Field(..., description="알림 제목")
    body: str = Field(..., description="알림 내용")


class FCMTokenParams(BaseModel):
    fcm_token: str = Field(..., description="FCM 토큰")


FCMTokenResponse = make_named_response(FCMToken, "FCMTokenResponse")

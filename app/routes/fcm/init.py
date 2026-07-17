import json
import os

from common.env_utils import getenvval
from common.logger_setup import get_logger

logger = get_logger()
googlefile = None


def init():
    global googlefile
    googlefile = getenvval("FCM_GOOGLE_FILE")
    if googlefile:
        if os.path.isfile(googlefile):
            with open(googlefile, "r", encoding="utf-8") as f:
                content = f.read()
                googlefile = json.loads(content)
                logger.info("FCM Google file content loaded successfully.")
        else:
            logger.error(
                "FCM_GOOGLE_FILE path %s does not exist or is not a file.",
                googlefile,
            )
            googlefile = None


def get_client_fcm_config() -> dict:
    """
    Minimal client-safe Firebase config (no full service JSON dump).
    """
    if not isinstance(googlefile, dict):
        return {}
    project_info = googlefile.get("project_info") or {}
    clients = googlefile.get("client") or []
    first = clients[0] if clients else {}
    client_info = first.get("client_info") or {}
    android = client_info.get("android_client_info") or {}
    api_keys = first.get("api_key") or []
    api_key = api_keys[0].get("current_key") if api_keys else None
    return {
        "project_id": project_info.get("project_id"),
        "messaging_sender_id": project_info.get("project_number"),
        "mobilesdk_app_id": client_info.get("mobilesdk_app_id"),
        "package_name": android.get("package_name"),
        "api_key": api_key,
    }

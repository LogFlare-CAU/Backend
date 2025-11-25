from common.env_utils import getenvval
from common.logger_setup import get_logger
import os
import json

logger = get_logger()
googlefile = None


def init():
    global googlefile
    googlefile = getenvval("FCM_GOOGLE_FILE")
    if googlefile:
        if os.path.isfile(googlefile):
            with open(googlefile, "r") as f:
                content = f.read()
                googlefile = json.loads(content)
                os.environ["FCM_GOOGLE_FILE"] = content
                logger.info("FCM Google file content loaded successfully.")
                logger.debug(f"FCM Google file content: {googlefile}")
                # Further processing of content can be done here
        else:
            logger.error(
                f"FCM_GOOGLE_FILE path {googlefile} does not exist or is not a file."
            )

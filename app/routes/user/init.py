from . import model, service
from common.sqlsession import async_session
from common import getenvval, hash_password
from common.enums import Permissions
import logging


logger = logging.getLogger("logflare")


async def init_superuser():
    """
    초기 슈러유저를 생성합니다.
    1번 유저가 존재하지 않으면 생성하고, 존재하면 권한을 관리자 권한으로 변경합니다.
    1번 유저의 이름과 비밀번호는 환경변수 SUPERUSER_NAME, SUPERUSER_PASSWORD에서 가져옵니다.
    1번 유저가 이미 존재하고 관리자 권한이면 아무 작업도 하지 않습니다.
    1번 유저의 기본 이름과 비밀번호는 admin, admin입니다.
    """
    user = getenvval("SUPERUSER_NAME")
    password = getenvval("SUPERUSER_PASSWORD")
    if not user or not password:
        logger.warning(
            "슈퍼유저 이름 또는 비밀번호가 설정되지 않았습니다. 슈퍼유저를 생성하지 않습니다."
        )
        return
    async with async_session() as conn:
        try:
            user = await service.get_user_byid(conn, 1)
            if user.permission < Permissions.ADMINISTRATOR:
                user.permission = Permissions.ADMINISTRATOR
                await conn.commit()
                logger.info(
                    "1번 사용자(슈퍼유저)의 권한이 관리자 권한으로 변경되었습니다."
                )
                return
            logger.info(
                "1번 사용자(슈퍼유저)가 이미 존재합니다. 아무 작업도 수행하지 않습니다."
            )
            return
        except:
            user = model.User(
                username=user,
                password=hash_password(password),
                permission=Permissions.ADMINISTRATOR,
            )
            conn.add(user)
            await conn.commit()
            logger.info(
                f"슈퍼유저 계정이 생성되었습니다({user}, {password}). 즉시 비밀번호를 바꿔주세요."
            )
            return

import json
import logging
from typing import List
from app.core.path import pkg_data_path

# 순환 참조 방지를 위해 안에서 import하거나 타입 체크용으로만 사용 시 TYPE_CHECKING
from app.models.dto import RoomKey
from app.repositories.room_repository import RoomRepository

logger = logging.getLogger("app")


# JSON 관련 imports 및 함수 제거

def load_rooms() -> List[RoomKey]:
    """
    Supabase DB에서 룸 정보를 조회하여 반환합니다.
    DB 연결 실패 시 예외를 발생시킵니다 (Fail Fast).
    """
    try:
        repo = RoomRepository()
        rooms = repo.get_all_rooms()
        
        if not rooms:
            logger.warning("DB connection successful but no rooms found.")
            return []
            
        return rooms
    except Exception as e:
        logger.error(
            f"Failed to load rooms from DB: {str(e)}",
            extra={"status": 500, "errorCode": "DB-Error"}
        )
        raise

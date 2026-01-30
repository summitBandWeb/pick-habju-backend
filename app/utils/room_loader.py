from app.core.database import supabase
from app.core.config import SUPABASE_TABLE
from typing import List, Dict, Any
from app.exception.api.room_loader_exception import RoomLoaderFailedError
from app.models.dto import RoomDetail
from postgrest.exceptions import APIError
from pydantic import ValidationError

def get_rooms_by_capacity(capacity: int) -> List[RoomDetail]:
    """
    Supabase에서 capacity 이상인 룸만 조회합니다.
    """
    try:
        response = (
            supabase.table("room")
            .select("*, branch(name)")
            .gte("max_capacity", capacity)  # gte: greater than or equal (>=)
            .execute()
        )
        
        target_rooms = [RoomDetail.model_validate(row) for row in response.data]
        return target_rooms

    except APIError as e:
        # Supabase API 오류 (쿼리, 권한 등)
        raise RoomLoaderFailedError(f"데이터베이스 쿼리 실패: {str(e)}")
    except ValidationError as e:
        # Pydantic validation 오류
        raise RoomLoaderFailedError(f"데이터 형식 오류: {str(e)}")
    except Exception as e:
        # 예상치 못한 오류
        raise RoomLoaderFailedError(f"알 수 없는 오류: {str(e)}")

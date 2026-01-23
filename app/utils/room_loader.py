from app.core.database import supabase
from typing import List, Dict, Any
from app.exception.api.room_loader_exception import RoomLoaderFailedError
from app.models.dto import RoomDetail

def get_rooms_by_capacity(capacity: int) -> List[RoomDetail]:
    """
    Supabase에서 capacity 이상인 룸만 조회합니다.
    """
    try:
        response = (
            supabase.table("v_full_info")  # 테이블 이름 확인 필요!
            .select("*")
            .gte("max_capacity", capacity)  # gte: greater than or equal (>=)
            .execute()
        )
        
        target_rooms = [RoomDetail.model_validate(row) for row in response.data]
        return target_rooms

    except Exception as e:
        raise RoomLoaderFailedError(f"룸 데이터 조회 실패: {str(e)}")
    

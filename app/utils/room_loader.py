from app.core.supabase_client import supabase
from app.core.config import SUPABASE_TABLE
from typing import List
from app.exception.api.room_loader_exception import RoomLoaderFailedError
from app.models.dto import RoomDetail
from postgrest.exceptions import APIError
from pydantic import ValidationError

def get_rooms_by_criteria(
    capacity: int,
    swLat: float,
    swLng: float,
    neLat: float,
    neLng: float
) -> List[RoomDetail]:
    """
    Supabase에서 capacity 이상인 룸만 조회합니다.
    """
    try:
        # Bounding Box 필터링 쿼리 수행 (인원수 조건 & 지도 범위 조건)
        response = (
            supabase.table("room")
            .select("*, branch!inner(name, lat, lng)")
            .gte("max_capacity", capacity)
            .gte("branch.lat", swLat)
            .lte("branch.lat", neLat)
            .gte("branch.lng", swLng)
            .lte("branch.lng", neLng)
            .execute()
        )

        target_rooms = []
        for row in response.data:
            # Data Flattening: branch 객체 내의 좌표를 상위로 추출
            if "branch" in row and isinstance(row["branch"], dict):
                row["lat"] = row["branch"].get("lat")
                row["lng"] = row["branch"].get("lng")
            
            # image_urls가 None인 경우 빈 리스트로 변환 (DTO 요구사항 준수)
            if row.get("image_urls") is None:
                row["image_urls"] = []
                
            target_rooms.append(RoomDetail.model_validate(row))
        return target_rooms

    except APIError as e:
        raise RoomLoaderFailedError(f"데이터베이스 쿼리 실패: {str(e)}")
    except ValidationError as e:
        raise RoomLoaderFailedError(f"데이터 형식 오류: {str(e)}")
    except Exception as e:
        raise RoomLoaderFailedError(f"알 수 없는 오류: {str(e)}")

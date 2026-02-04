from app.core.supabase_client import supabase
from app.core.config import SUPABASE_TABLE
from typing import List, Optional
from app.exception.api.room_loader_exception import RoomLoaderFailedError
from app.models.dto import RoomDetail
from postgrest.exceptions import APIError
from pydantic import ValidationError

# NOTE: API 레벨에서는 좌표가 필수(Mandatory)이지만, 기존 유닛 테스트 코드들과의 
# 하위 호환성을 위해 내부 유틸리티 함수에서는 Optional로 유지합니다. 
# 추후 모든 테스트 코드에 Dummy 좌표를 적용한 뒤 필수값으로 리팩토링 예정입니다.
def get_rooms_by_criteria(
    capacity: int,
    swLat: Optional[float] = None,
    swLng: Optional[float] = None,
    neLat: Optional[float] = None,
    neLng: Optional[float] = None
) -> List[RoomDetail]:

    """
    Supabase에서 capacity 이상인 룸만 조회합니다.
    좌표가 주어지면 해당 범위 내의 룸만 필터링합니다.
    """
    try:
        # 기본 쿼리: 인원수 조건 & Branch 정보 Join
        query = supabase.table("room").select("*, branch!inner(name, lat, lng)").gte("max_capacity", capacity)

        # 지도 좌표 영역 필터링 (좌표가 모두 있을 때만 수행)
        if all(v is not None for v in [swLat, swLng, neLat, neLng]):
            query = (
                query
                .gte("branch.lat", swLat)
                .lte("branch.lat", neLat)
                .gte("branch.lng", swLng)
                .lte("branch.lng", neLng)
            )

        response = query.execute()

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

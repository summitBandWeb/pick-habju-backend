import logging
from typing import List, Optional

from postgrest.exceptions import APIError
from pydantic import ValidationError

from app.core.constants import is_in_service_area
from app.core.supabase_client import get_async_supabase_client
from app.exception.api.room_loader_exception import RoomLoaderFailedError
from app.models.dto import RoomDetail

logger = logging.getLogger(__name__)


async def get_rooms_by_criteria(
    capacity: int,
    swLat: Optional[float] = None,
    swLng: Optional[float] = None,
    neLat: Optional[float] = None,
    neLng: Optional[float] = None,
) -> List[RoomDetail]:
    """
    Supabase에서 capacity 이상인 룸을 조회합니다.
    서비스 지역(역 기준 2km 반경) 내의 룸만 반환합니다.
    좌표가 주어지면 해당 범위 내의 룸만 추가 필터링합니다.
    """
    try:
        supabase = await get_async_supabase_client()
        # Deploy 환경마다 branch 컬럼 반영 시점이 다를 수 있어 select를 순차 fallback.
        # !inner 조인으로 branch 테이블 조건을 room 조회에 반영.
        select_candidates = [
            "*, branch!inner(name, lat, lng, phone_number, display_name)",
            "*, branch!inner(name, lat, lng)",
        ]

        response = None
        last_error: Optional[Exception] = None
        for select_expr in select_candidates:
            try:
                query = supabase.table("room").select(select_expr).gte("max_capacity", capacity)
                
                # DB 레벨 필터링 (위경도 지도 경계 조건) - 병목 해소
                if all(v is not None for v in [swLat, swLng, neLat, neLng]):
                    # 포스트그레스트에서 외래키 필터링 시 테이블명.컬럼명 형식 사용
                    query = query.gte("branch.lat", swLat).lte("branch.lat", neLat).gte("branch.lng", swLng).lte("branch.lng", neLng)

                response = await query.execute()
                break
            except APIError as e:
                last_error = e
                # undefined_column(42703)만 fallback, 나머지 API 에러는 즉시 중단.
                if "42703" not in str(e):
                    raise
                continue

        if response is None:
            raise last_error if last_error else RoomLoaderFailedError("데이터베이스 쿼리 실패")

        target_rooms: List[RoomDetail] = []
        for row in response.data:
            branch = row.get("branch")
            if isinstance(branch, dict):
                row["lat"] = branch.get("lat")
                row["lng"] = branch.get("lng")
                row["phone_number"] = branch.get("phone_number")
                row["display_name"] = branch.get("display_name")
            else:
                row["branch"] = RoomDetail.BRANCH_FALLBACK_NAME
                row["lat"] = None
                row["lng"] = None
                row["phone_number"] = None
                row["display_name"] = None

            lat = row.get("lat")
            lng = row.get("lng")

            # 서비스 지역 필터: 좌표가 없거나 반경 밖이면 제외
            if lat is None or lng is None or not is_in_service_area(lat, lng):
                continue

            # 지도 경계 필터 (클라이언트가 좌표 범위를 지정한 경우)
            if all(v is not None for v in [swLat, swLng, neLat, neLng]):
                if not (swLat <= lat <= neLat and swLng <= lng <= neLng):
                    continue

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

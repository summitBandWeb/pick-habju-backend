from typing import List, Optional

from postgrest.exceptions import APIError
from pydantic import ValidationError

from app.core.supabase_client import supabase
from app.exception.api.room_loader_exception import RoomLoaderFailedError
from app.models.dto import RoomDetail


def get_rooms_by_criteria(
    capacity: int,
    swLat: Optional[float] = None,
    swLng: Optional[float] = None,
    neLat: Optional[float] = None,
    neLng: Optional[float] = None,
) -> List[RoomDetail]:
    """
    Supabase에서 capacity 이상인 룸을 조회합니다.
    좌표가 주어지면 해당 범위 내의 룸만 필터링합니다.
    """
    try:
        # Deploy 환경마다 branch 컬럼 반영 시점이 다를 수 있어 select를 순차 fallback.
        select_candidates = [
            "*, branch(name, lat, lng, phone_number, display_name, open_wait_rule)",
            "*, branch(name, lat, lng, phone_number, display_name)",
            "*, branch(name, lat, lng)",
        ]

        response = None
        last_error: Optional[Exception] = None
        for select_expr in select_candidates:
            try:
                response = (
                    supabase.table("room")
                    .select(select_expr)
                    .gte("max_capacity", capacity)
                    .execute()
                )
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
                row["open_wait_rule"] = branch.get("open_wait_rule")
            else:
                row["branch"] = RoomDetail.BRANCH_FALLBACK_NAME
                row["lat"] = None
                row["lng"] = None
                row["phone_number"] = None
                row["display_name"] = None
                row["open_wait_rule"] = {}

            # branch 좌표가 있는 경우에만 지도 경계 필터 적용.
            if all(v is not None for v in [swLat, swLng, neLat, neLng]):
                lat = row.get("lat")
                lng = row.get("lng")
                if lat is not None and lng is not None:
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

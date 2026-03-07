import logging
import os
from typing import List, Optional

from postgrest.exceptions import APIError
from pydantic import ValidationError

from app.core.constants import PRIORITY_AREA_BUSINESS_IDS, MAX_EXCLUDED_PRICE_PER_HOUR
from app.core.supabase_client import supabase
from app.exception.api.room_loader_exception import RoomLoaderFailedError
from app.models.dto import RoomDetail

logger = logging.getLogger(__name__)


def _is_priority_area_filter_enabled() -> bool:
    raw = (os.getenv("PRIORITY_AREA_ONLY_FILTER", "true") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_priority_area_business_ids() -> List[str]:
    env_raw = (os.getenv("PRIORITY_AREA_BUSINESS_IDS") or "").strip()
    if env_raw:
        return [v.strip() for v in env_raw.split(",") if v and v.strip()]
    return list(PRIORITY_AREA_BUSINESS_IDS)


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
            "*, branch(name, lat, lng, phone_number, display_name, open_wait_rule, standby_days)",
            "*, branch(name, lat, lng, phone_number, display_name, open_wait_rule)",
            "*, branch(name, lat, lng, phone_number, display_name)",
            "*, branch(name, lat, lng)",
        ]

        response = None
        last_error: Optional[Exception] = None
        allowed_business_ids = _resolve_priority_area_business_ids()
        use_priority_filter = _is_priority_area_filter_enabled() and bool(allowed_business_ids)
        for select_expr in select_candidates:
            try:
                query = supabase.table("room").select(select_expr).gte("max_capacity", capacity)
                if use_priority_filter:
                    query = query.in_("business_id", allowed_business_ids)
                response = query.execute()
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
                row["standby_days"] = branch.get("standby_days")
            else:
                row["branch"] = RoomDetail.BRANCH_FALLBACK_NAME
                row["lat"] = None
                row["lng"] = None
                row["phone_number"] = None
                row["display_name"] = None
                row["open_wait_rule"] = {}
                row["standby_days"] = None

            # branch 좌표가 있는 경우에만 지도 경계 필터 적용.
            if all(v is not None for v in [swLat, swLng, neLat, neLng]):
                lat = row.get("lat")
                lng = row.get("lng")
                if lat is not None and lng is not None:
                    if not (swLat <= lat <= neLat and swLng <= lng <= neLng):
                        continue

            if row.get("image_urls") is None:
                row["image_urls"] = []

            room = RoomDetail.model_validate(row)

            # 시간당 가격이 임계치 이하인 룸은 조회 결과에서 제외
            # NOTE: 크롤러 LLM 파싱 단에서 드럼스틱·기타 대여 등 악세사리 예약 페이지 또는 예약 탭을 활용한 공지사항(0원 또는 999,999 등 설정)이 합주실로 잘못 수집될 수 있음.
            #       price_per_hour <= MIN_VALID_PRICE_PER_HOUR 인 경우는 신뢰할 수 없는 데이터로 간주하여 필터링함.
            
            if room.pricePerHour <= MAX_EXCLUDED_PRICE_PER_HOUR:
                # NOTE: 쿼리 레이어에서 걸러내기 어려운 악세사리 예약 데이터를 방어적으로 필터링함.
                #       재발 시 크롤러 파싱 로직 점검 필요.
                logger.warning(
                    f"[metrics] room_filter.excluded: reason=price_too_low "
                    f"biz_item_id={room.biz_item_id} price_per_hour={room.pricePerHour}"
                )
                continue

            target_rooms.append(room)

        return target_rooms

    except APIError as e:
        raise RoomLoaderFailedError(f"데이터베이스 쿼리 실패: {str(e)}")
    except ValidationError as e:
        raise RoomLoaderFailedError(f"데이터 형식 오류: {str(e)}")
    except Exception as e:
        raise RoomLoaderFailedError(f"알 수 없는 오류: {str(e)}")

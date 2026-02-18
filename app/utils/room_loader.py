from app.core.supabase_client import supabase
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
        # v2.0.0: price_config, min_capacity 관련 필드 및 branch 전화번호, rule 등 추가 조회
        # NOTE: branch 테이블의 컬럼들이 마이그레이션 되어 있어야 함
        query = supabase.table("room").select(
            # left join으로 branch 정보가 누락된 room도 조회되게 유지
            "*, branch(name, lat, lng, phone_number, display_name, open_wait_rule)"
        ).gte("max_capacity", capacity)

        response = query.execute()

        target_rooms = []
        for row in response.data:
            # Data Flattening: branch 객체 내의 정보를 상위로 추출
            if "branch" in row and isinstance(row["branch"], dict):
                row["lat"] = row["branch"].get("lat")
                row["lng"] = row["branch"].get("lng")
                # v2.0.0 Branch Info
                row["phone_number"] = row["branch"].get("phone_number")
                row["display_name"] = row["branch"].get("display_name")
                row["open_wait_rule"] = row["branch"].get("open_wait_rule")
            else:
                row["branch"] = RoomDetail.BRANCH_FALLBACK_NAME
                row["lat"] = None
                row["lng"] = None
                row["phone_number"] = None
                row["display_name"] = None
                row["open_wait_rule"] = {}

            # 좌표 필터는 branch 좌표가 존재할 때만 적용.
            # branch 누락 room은 fallback 목적상 결과에서 제외하지 않음.
            if all(v is not None for v in [swLat, swLng, neLat, neLng]):
                lat = row.get("lat")
                lng = row.get("lng")
                if lat is not None and lng is not None:
                    if not (swLat <= lat <= neLat and swLng <= lng <= neLng):
                        continue
            
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

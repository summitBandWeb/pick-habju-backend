from typing import List

from app.models.dto import RoomDetail
from app.validate.hour_validator import validate_hour_slots
from app.validate.room_detail_validator import validate_room_detail_list


def validate_availability_request(
    date: str,
    hour_slots: List[str],
    target_rooms: List[RoomDetail],
):
    """
    요청의 비즈니스 로직 유효성을 검증합니다.
    (DTO에서 처리하지 못한 복합 검증을 수행)

    1. 시간 슬롯 연속성 검증(1시간 단위)
    2. RoomDetail 리스트 검증
    """
    # NOTE:
    # - 날짜/시간 형식: AvailabilityRequest DTO에서 이미 검증됨
    # - 좌표 유효성: AvailabilityRequest DTO에서 이미 검증됨

    # 시간 슬롯 연속성 검증(13:00, 14:00, 15:00...)
    # DTO는 개별 필드 검증에 집중하므로 슬롯 간 관계 검증은 여기서 수행
    validate_hour_slots(hour_slots, date)

    # RoomKey 관련 모든 검증을 한 번에 처리
    # 빈 target_rooms는 "검색 결과 없음" 정상 시나리오이므로 예외로 처리하지 않는다.
    if target_rooms:
        validate_room_detail_list(target_rooms)

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
    요청의 비즈니스 로직 유효성을 검사합니다.
    (DTO에서 처리하지 못하는 복합 검증 수행)

    1. 시간 슬롯 연속성 검증 (1시간 단위)
    2. RoomDetail 리스트 검증
    """
    # NOTE: 
    # - 날짜/시간 포맷: AvailabilityRequest DTO에서 정규식으로 이미 검증됨
    # - 좌표 유효성: AvailabilityRequest DTO에서 이미 검증됨
    
    # 시간 슬롯 연속성 검증 (13:00, 14:00, 15:00...)
    # DTO는 개별 필드 검증에 집중하므로, 슬롯 간 관계 검증은 여기서 수행
    validate_hour_slots(hour_slots, date)

    # DB 조회 결과 검증
    validate_room_detail_list(target_rooms)

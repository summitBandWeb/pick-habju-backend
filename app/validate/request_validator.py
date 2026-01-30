from typing import List
from app.models.dto import RoomDetail
from app.validate.date_validator import validate_date
from app.validate.hour_validator import validate_hour_slots
from app.validate.room_detail_validator import validate_room_detail_list

def validate_availability_request(
        date: str,
        hour_slots: List[str],
        target_rooms: List[RoomDetail],
):
    """
    요청의 유효성을 검사합니다.
    • 날짜 포맷 및 유효성 검증
    • 시간 슬롯 포맷 및 과거/연속성 검증
    • room detail 리스트 및 개별 room detail 검증
    """
    validate_date(date)
    validate_hour_slots(hour_slots, date)

    # RoomKey 관련 모든 검증을 한 번에 처리
    validate_room_detail_list(target_rooms)

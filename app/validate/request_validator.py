from typing import List
from app.models.dto import RoomKey
from app.validate.date_validator import validate_date
from app.validate.hour_validator import validate_hour_slots
from app.validate.roomkey_validator import validate_room_key_list # 수정된 부분

def validate_availability_request(
        date: str,
        hour_slots: List[str],
        rooms: List[RoomKey],
):
    """
    요청의 유효성을 검사합니다.
    • 날짜 포맷 및 유효성 검증
    • 시간 슬롯 포맷 및 과거/연속성 검증
    • room 키 리스트 및 개별 room 키 검증
    """
    validate_date(date)
    validate_hour_slots(hour_slots, date)

    # RoomKey 관련 모든 검증을 한 번에 처리
    validate_room_key_list(rooms)

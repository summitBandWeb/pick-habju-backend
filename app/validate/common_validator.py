
from typing import List
from app.models.dto import RoomKey
from app.validate.date_validator import validate_date
from app.validate.hour_validator import validate_hour_slots
from app.validate.roomkey_validator import validate_room_key

def validate_availability_request(
    date: str,
    hour_slots: List[str],
    rooms: List[RoomKey],
):
    """
    • 날짜 포맷 및 유효성 검증
    • 시간 슬롯 포맷 및 과거/연속성 검증
    • room 키 검증
    """
    validate_date(date)
    validate_hour_slots(hour_slots, date)
    if not rooms:
        raise ValueError("rooms 목록이 비어 있습니다.")
    for room in rooms:
        validate_room_key(room)

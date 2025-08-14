from typing import List
from app.models.dto import RoomKey
from app.validate.date_validator import validate_date
from app.validate.hour_validator import validate_hour_slots
from app.validate.roomkey_validator import validate_room_key

def validate_availability_request(date: str, hour_slots: List[str], rooms: List[RoomKey]):
    """
    메인 예약 가능 여부 요청 파라미터를 한 곳에서 검증합니다.
    """
    # 날짜 형식 및 로직 검증
    validate_date(date)

    # 시간 슬롯 형식 및 로직 검증
    validate_hour_slots(hour_slots, date)

    # 요청에 제공된 각 룸 키 검증
    for room in rooms:
        validate_room_key(room)

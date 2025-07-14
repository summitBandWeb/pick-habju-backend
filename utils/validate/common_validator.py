import re
from typing import List
from datetime import datetime, date as dt_date
from utils.room_loader import load_rooms
from models.dto import RoomKey
from exception.common_exception import InvalidDateFormatError, InvalidHourSlotError, InvalidRoomKeyError

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
HOUR_PATTERN = r"^\d{2}:\d{2}$"

def validate_date(date: str):
    if not re.match(DATE_PATTERN, date):
        raise InvalidDateFormatError(f"날짜 형식이 잘못되었습니다: {date}")
    # 과거 날짜 체크
    today = dt_date.today()
    input_date = datetime.strptime(date, "%Y-%m-%d").date()
    if input_date < today:
        raise InvalidDateFormatError(f"과거 날짜는 허용되지 않습니다: {date}")

def validate_hour_slots(hour_slots: List[str], date: str):
    # date 파라미터 추가
    now = datetime.now()
    today = now.date()
    input_date = datetime.strptime(date, "%Y-%m-%d").date()
    for slot in hour_slots:
        if not re.match(HOUR_PATTERN, slot):
            raise InvalidHourSlotError(f"시간 형식이 잘못되었습니다: {slot}")
        if input_date == today:
            slot_time = datetime.strptime(slot, "%H:%M").time()
            if slot_time < now.time():
                raise InvalidHourSlotError(f"과거 시간은 허용되지 않습니다: {slot}")

def validate_room_key(room: RoomKey):
    if not room.business_id or not room.biz_item_id or not room.name or not room.branch:
        raise InvalidRoomKeyError(f"RoomKey 정보가 누락되었습니다: {room}")

    # rooms.json에서 RoomKey 목록 불러오기
    rooms = load_rooms()
    # RoomKey가 rooms.json에 존재하는지 확인
    found = any(
        r["name"] == room.name and
        r["branch"] == room.branch and
        str(r["business_id"]) == str(room.business_id) and
        str(r["biz_item_id"]) == str(room.biz_item_id)
        for r in rooms
    )
    if not found:
        raise InvalidRoomKeyError(f"RoomKey가 rooms.json에 존재하지 않습니다: {room}")
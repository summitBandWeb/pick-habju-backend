import pytest
from utils.validate.common_validator import (
    validate_date, validate_hour_slots, validate_room_key,
)
from exception.common_exception import (
    InvalidDateFormatError, InvalidHourSlotError, InvalidRoomKeyError
)
from models.dto import RoomKey
from datetime import datetime, timedelta

def test_validate_date_valid():
    """오늘 날짜(YYYY-MM-DD 형식)는 유효한 날짜로 통과해야 한다."""
    today = datetime.now().strftime("%Y-%m-%d")
    # 정상 케이스
    validate_date(today)

def test_validate_date_invalid_format():
    """'YYYY/MM/DD' 형식은 잘못된 날짜형식으로 간주되어 InvalidDateFormatError 예외를 발생시켜야 한다."""
    with pytest.raises(InvalidDateFormatError):
        validate_date("2024/07/01")  # 잘못된 형식

def test_validate_date_past():
    """과거 날짜는 선택할 수 없으며 InvalidDateFormatError 예외가 발생해야 한다."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    with pytest.raises(InvalidDateFormatError):
        validate_date(yesterday)  # 과거 날짜

# validate_hour_slots 테스트
def test_validate_hour_slots_valid_today():
    """오늘 날짜 기준으로 현재 시각 이후의 시간대는 유효한 슬롯으로 통과되어야 한다."""
    now = datetime.now()
    # 현재 시간보다 1시간 뒤
    slot = (now + timedelta(hours=1)).strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")
    validate_hour_slots([slot], today)

def test_validate_hour_slots_invalid_format():
    """'9:00' 형식은 잘못된 시간 형식이며 InvalidHourSlotError 예외가 발생해야 한다 (정규식 미통과)."""
    today = datetime.now().strftime("%Y-%m-%d")
    with pytest.raises(InvalidHourSlotError):
        validate_hour_slots(["9:00"], today)  # 잘못된 형식

def test_validate_hour_slots_past_time_today():
    """오늘 날짜인데 과거 시간대를 포함하면 InvalidHourSlotError 예외가 발생해야 한다."""
    now = datetime.now()
    # 현재 시간보다 1시간 전
    slot = (now - timedelta(hours=1)).strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")
    with pytest.raises(InvalidHourSlotError):
        validate_hour_slots([slot], today)

def test_validate_hour_slots_future_date():
    """미래 날짜라면 시간 값이 과거든 현재든 관계없이 모두 유효한 슬롯으로 인정된다."""
    future_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    validate_hour_slots(["00:00", "23:59"], future_date)

def test_validate_room_key_valid():
    """rooms.json에 존재하는 RoomKey만 통과해야 한다."""
    valid_room = RoomKey(name="Classic", branch="비쥬합주실 3호점", business_id="917236", biz_item_id="5098039")
    validate_room_key(valid_room)

def test_validate_room_key_not_in_json():
    """rooms.json에 없는 RoomKey는 InvalidRoomKeyError 예외가 발생해야 한다."""
    invalid_room = RoomKey(name="없는방", branch="없는지점", business_id="000", biz_item_id="000")
    with pytest.raises(InvalidRoomKeyError):
        validate_room_key(invalid_room)
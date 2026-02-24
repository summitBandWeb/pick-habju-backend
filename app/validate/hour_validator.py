import re
from datetime import datetime
from typing import List

from app.exception.common.hour_exception import (
    HourDiscontinuousError,
    InvalidHourSlotError,
    PastHourSlotNotAllowedError,
)

HOUR_PATTERN = r"^(?:[01]\d|2[0-4]):00$"


def validate_hour_slot_format(slot: str):
    """시간 형식(HH:MM) 검증"""
    if not re.match(HOUR_PATTERN, slot):
        raise InvalidHourSlotError(f"시간 형식이 잘못되었습니다: {slot}")
    if slot == "24:00":
        # 24:00 is a valid end-of-day boundary marker.
        return


def validate_hour_slot_not_past(slot: str, now_time):
    """슬롯이 과거 시간인지 검증"""
    validate_hour_slot_format(slot)
    slot_minutes = _slot_to_minutes(slot)

    # now_time 이 문자열(요청 날짜)인지 time 객체인지 구분
    if isinstance(now_time, str):
        input_date = datetime.strptime(now_time, "%Y-%m-%d").date()
        today = datetime.now().date()
        if input_date > today:
            return  # 미래 날짜는 시간 비교 불필요
        now_time = datetime.now().time()

    now_minutes = now_time.hour * 60 + now_time.minute
    if slot_minutes <= now_minutes:
        raise PastHourSlotNotAllowedError(f"과거 시간은 허용되지 않습니다: {slot}")


def validate_hour_slots(hour_slots: List[str], date: str):
    """시간 슬롯 전체 검증(형식 + 과거여부 + 연속성)"""
    now = datetime.now()
    today = now.date()
    input_date = datetime.strptime(date, "%Y-%m-%d").date()

    for slot in hour_slots:
        validate_hour_slot_format(slot)
        if input_date == today:
            validate_hour_slot_not_past(slot, now.time())

    validate_hour_continuous(hour_slots, date)


def validate_hour_continuous(hour_slots: List[str], date: str):
    """입력받은 시간 슬롯들이 1시간 단위로 끊기지 않고 연속적인지 검증합니다.

    Args:
        hour_slots (List[str]): 검사할 시간 슬롯 문자열 배열 (예: ["23:00", "24:00", "01:00"]).
        date (str): 예약 기준 날짜 (YYYY-MM-DD 형식). 시그니처 유지를 위해 존재함.

    Raises:
        HourDiscontinuousError: 슬롯 간격이 1시간을 초과하여 중간에 빈 시간이 있는 경우 발생.

    Rationale (의도):
        사용자가 선택한 개별 시간 단위(1시간)가 중간에 이가 빠지지 않고 이어져 있는지 
        확인하기 위한 필수 검수 과정입니다. 자정을 넘기는 교차 시간대의 경우,
        새벽 시간대 슬롯(04:00 이하)에 1440분(하루)을 더해 연속성 정렬 오류를 방지하도록 구현되었습니다.
    """
    _ = date
    if len(hour_slots) <= 1:
        return

    for slot in hour_slots:
        validate_hour_slot_format(slot)

    raw_slots = [_slot_to_minutes(slot) for slot in hour_slots]
    
    # 최대 예약 허용 시간은 5시간이므로, 자정을 넘기는 케이스는
    # 20:00(1200분) ~ 04:00(240분) 사이에만 발생할 수 있음
    has_late_night = any(s >= 1200 for s in raw_slots)   # 20:00 이후
    has_early_morning = any(s <= 240 for s in raw_slots) # 04:00 이전
    
    # 두 시간대가 공존하면 새벽 시간대(04:00 이하)를 다음 날로 간주하여 1440을 더함
    if has_late_night and has_early_morning:
        slots = sorted((s + 1440 if s <= 240 else s) for s in raw_slots)
    else:
        slots = sorted(raw_slots)

    for i in range(len(slots) - 1):
        if slots[i + 1] - slots[i] != 60:
            raise HourDiscontinuousError("시간 슬롯이 1시간 단위로 연속적이지 않습니다.")


def _slot_to_minutes(slot: str) -> int:
    """HH:MM 문자열을 분 단위 정수로 변환"""
    # This helper assumes slot already passed HOUR_PATTERN validation.
    # AvailabilityService._slot_to_minutes performs strict regex/range validation.
    try:
        hour, minute = slot.split(":")
        return int(hour) * 60 + int(minute)
    except (ValueError, AttributeError) as exc:
        raise InvalidHourSlotError(f"시간 형식이 잘못되었습니다: {slot}") from exc

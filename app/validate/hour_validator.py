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
    """입력받은 시간값이 연속인지 검증"""
    _ = date
    if len(hour_slots) <= 1:
        return

    for slot in hour_slots:
        validate_hour_slot_format(slot)

    slots = sorted(_slot_to_minutes(slot) for slot in hour_slots)

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

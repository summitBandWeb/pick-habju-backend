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

    is_overnight = False
    if input_date == today:
        raw_minutes = [_slot_to_minutes(s) for s in hour_slots if re.match(HOUR_PATTERN, s)]
        has_late_night = any(m >= 1140 for m in raw_minutes)   # 19:00 이후
        has_early_morning = any(m <= 300 for m in raw_minutes)  # 05:00 이전
        # Rationale: 23:00~01:00처럼 자정을 넘기는 overnight 예약에서
        #            00:00, 01:00 등 새벽 슬롯은 실제로 "다음날" 시간임.
        #            today 기준 과거 시간 비교를 적용하면 오탐이 발생하므로 스킵함.
        #            validate_hour_continuous와 동일한 19:00/05:00 기준을 사용.
        is_overnight = has_late_night and has_early_morning

    for slot in hour_slots:
        validate_hour_slot_format(slot)
        if input_date == today:
            if is_overnight and _slot_to_minutes(slot) <= 300:
                continue  # 다음날 새벽 슬롯은 과거 비교 제외
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
    
    # [자정을 넘기는 연속성 검사 기준 (19:00 ~ 05:00)]
    # DTO 계층에서 허용하는 최대 예약 시간은 5시간입니다.
    # 가장 극단적인 심야 예약 조합은 "19:00 ~ 00:00(24:00)"에서 시작해, 가장 늦게 끝나는 조합이 "00:00 ~ 05:00"입니다.
    # 즉, 정상적인 5시간 이내의 예약이라면 '19:00 이전' 시간대와 '05:00 이후' 시간대가 같은 슬롯 배열에 공존할 수 없습니다.
    # 따라서 19:00(1140분) 이후 값을 "심야", 05:00(300분) 이전 값을 "새벽"으로 정의하여 교차 여부를 판별합니다.
    has_late_night = any(s >= 1140 for s in raw_slots)   # 19:00 이후 슬롯 존재 여부
    has_early_morning = any(s <= 300 for s in raw_slots) # 05:00 이전 슬롯 존재 여부
    
    # 심야(19:00~)와 새벽(~05:00) 시간대가 배열에 공존한다면 자정을 넘긴(Overnight) 예약입니다.
    # 00:00~04:00과 같은 새벽 슬롯들은 숫자가 작아 정렬 시 앞으로 오게 되므로 시계열 연속성이 깨집니다.
    # 이를 방지하기 위해 새벽 시간대값에 하루치인 1440분을 더해 익일 시간(예: 01:00 -> 25:00)으로 변환 후 정렬합니다.
    if has_late_night and has_early_morning:
        slots = sorted((s + 1440 if s <= 300 else s) for s in raw_slots)
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

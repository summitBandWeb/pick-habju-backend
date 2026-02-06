import pytest
from app.validate.hour_validator import validate_hour_slot_format, validate_hour_slot_not_past, validate_hour_continuous
from app.exception.common.hour_exception import InvalidHourSlotError, PastHourSlotNotAllowedError, HourDiscontinuousError
from datetime import datetime, timedelta

# 형식 실패 케이스
def test_validate_hour_slots_invalid_format():
    """'9:00' 형식은 잘못된 시간 형식이며 InvalidHourSlotError 예외가 발생해야 한다 (정규식 미통과)."""
    with pytest.raises(InvalidHourSlotError):
        validate_hour_slot_format("9:00")  # 잘못된 형식

# 과거시간대 검증 성공 케이스
def test_validate_hour_slots_valid_today():
    """오늘 날짜 기준으로 현재 시각 이후의 시간대는 유효한 슬롯으로 통과되어야 한다."""
    now = datetime.now()
    if now.hour >= 23:
        pytest.skip("밤 11시 이후에는 날짜 변경 문제로 테스트를 건너뜁니다.")
    # 현재 시간보다 1시간 뒤
    slot = (now + timedelta(hours=1)).strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")
    validate_hour_slot_not_past(slot, today)

def test_validate_hour_slots_future_date():
    """미래 날짜라면 시간 값이 과거든 현재든 관계없이 모두 유효한 슬롯으로 인정된다."""
    future_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    validate_hour_slot_not_past("23:00", future_date)

# 과거시간대 검증 실패 케이스
def test_validate_hour_slots_past_time_today():
    """오늘 날짜인데 과거 시간대를 포함하면 PastHourSlotNotAllowedError 예외가 발생해야 한다."""
    now = datetime.now()
    # 현재 시간보다 1시간 전
    slot = (now - timedelta(hours=1)).strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")
    with pytest.raises(PastHourSlotNotAllowedError):
        validate_hour_slot_not_past(slot, today)

def test_validate_hour_continuous_valid():
    """연속적인 시간 슬롯이면 정상 통과한다."""
    date = datetime.now().strftime("%Y-%m-%d")
    slots = ["09:00", "10:00", "11:00"]
    validate_hour_continuous(slots, date)  # 예외 없어야 함

def test_validate_hour_continuous_invalid_gap():
    """시간 슬롯 간격이 1시간이 아니면 HourDiscontinuousError 예외가 발생한다."""
    date = datetime.now().strftime("%Y-%m-%d")
    slots = ["09:00", "11:00", "12:00"]  # 09시, 11시 사이 간격 2시간
    with pytest.raises(HourDiscontinuousError):
        validate_hour_continuous(slots, date)

def test_validate_hour_continuous_unsorted_slots():
    """정렬되지 않은 연속 시간 슬롯도 정상 통과한다."""
    date = datetime.now().strftime("%Y-%m-%d")
    slots = ["11:00", "09:00", "10:00"]
    validate_hour_continuous(slots, date)  # 정렬은 내부에서 처리

def test_validate_hour_continuous_single_slot():
    """하나의 시간 슬롯만 있으면 연속성 검사 통과."""
    date = datetime.now().strftime("%Y-%m-%d")
    slots = ["09:00"]
    validate_hour_continuous(slots, date)


def test_validate_hour_slots_equal_time_should_fail():
    """요청 시각과 슬롯이 동일하면 과거로 간주되어 실패해야 한다."""
    now = datetime.now()
    slot = now.strftime("%H:%M")
    with pytest.raises(PastHourSlotNotAllowedError):
        validate_hour_slot_not_past(slot, now.time())

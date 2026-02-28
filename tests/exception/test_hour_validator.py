from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.exception.common.hour_exception import (
    HourDiscontinuousError,
    InvalidHourSlotError,
    PastHourSlotNotAllowedError,
)
from app.validate.hour_validator import (
    validate_hour_continuous,
    validate_hour_slot_format,
    validate_hour_slot_not_past,
    validate_hour_slots,
)


def test_validate_hour_slots_invalid_format():
    with pytest.raises(InvalidHourSlotError):
        validate_hour_slot_format("9:00")


def test_validate_hour_slots_valid_today():
    now = datetime.now()
    if now.hour >= 23:
        pytest.skip("Near midnight boundary")

    slot = f"{(now.hour + 1):02d}:00"
    today = now.strftime("%Y-%m-%d")
    validate_hour_slot_not_past(slot, today)


def test_validate_hour_slots_future_date():
    future_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    validate_hour_slot_not_past("23:00", future_date)


def test_validate_hour_slots_past_time_today():
    now = datetime.now()
    if now.hour < 1:
        # 새벽 1시 이전에는 1시간 전이 전날이 되므로 테스트를 위해 고정 시간을 사용하거나 건너뜁니다.
        # 여기서는 단순히 00:00 슬롯이 현재(00:xx)보다 과거임을 테스트합니다.
        slot = "00:00"
        if now.minute == 0:
            pytest.skip("00:00 정각에는 과거 시간 테스트가 어려워 건너뜁니다.")
    else:
        # 현재 시간보다 1시간 전
        slot = f"{(now - timedelta(hours=1)).hour:02d}:00"

    today = now.strftime("%Y-%m-%d")
    with pytest.raises(PastHourSlotNotAllowedError):
        validate_hour_slot_not_past(slot, today)


def test_validate_hour_slot_not_past_invalid_format():
    with pytest.raises(InvalidHourSlotError):
        validate_hour_slot_not_past("bad-slot", datetime.now().strftime("%Y-%m-%d"))


def test_validate_hour_continuous_valid():
    date = datetime.now().strftime("%Y-%m-%d")
    slots = ["09:00", "10:00", "11:00"]
    validate_hour_continuous(slots, date)


def test_validate_hour_continuous_invalid_gap():
    date = datetime.now().strftime("%Y-%m-%d")
    slots = ["09:00", "11:00", "12:00"]
    with pytest.raises(HourDiscontinuousError):
        validate_hour_continuous(slots, date)


def test_validate_hour_continuous_unsorted_slots():
    date = datetime.now().strftime("%Y-%m-%d")
    slots = ["11:00", "09:00", "10:00"]
    validate_hour_continuous(slots, date)


def test_validate_hour_continuous_single_slot():
    date = datetime.now().strftime("%Y-%m-%d")
    slots = ["09:00"]
    validate_hour_continuous(slots, date)


def test_validate_hour_slots_equal_time_should_fail():
    now = datetime.now()
    fixed_now = now.replace(minute=0, second=0, microsecond=0)
    slot = fixed_now.strftime("%H:%M")
    today = fixed_now.strftime("%Y-%m-%d")

    with pytest.raises(PastHourSlotNotAllowedError):
        validate_hour_slot_not_past(slot, today)


class TestOvernightValidation:
    """자정 교차(overnight) 예약 슬롯 과거 검증 테스트"""

    def test_overnight_today_early_morning_slots_are_not_rejected(self):
        """오늘 날짜 23:00~01:00 예약 시 자정 이후 슬롯은 과거 판정하지 않아야 함

        Rationale:
            23:00~01:00은 다음날 새벽 슬롯(00:00, 01:00)을 포함하므로
            today 기준 과거 시간 비교에서 제외되어야 함.
            NOTE: datetime.now()를 22:00으로 고정하여 시간 의존성을 제거함.
        """
        fixed_now = datetime.now().replace(hour=22, minute=0, second=0, microsecond=0)
        today = fixed_now.strftime("%Y-%m-%d")
        slots = ["23:00", "00:00", "01:00"]
        with patch("app.validate.hour_validator.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.strptime.side_effect = datetime.strptime
            # 예외 없이 통과해야 함
            validate_hour_slots(slots, today)

    def test_non_overnight_today_past_slot_is_still_rejected(self):
        """overnight이 아닌 일반 오늘 예약에서는 과거 슬롯이 여전히 거부되어야 함

        Rationale:
            overnight 스킵 로직이 일반 과거 시간 검증을 약화시키지 않는지 회귀 방지.
            NOTE: datetime.now()를 14:00으로 고정하여 시간 의존성을 제거함.
        """
        fixed_now = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
        today = fixed_now.strftime("%Y-%m-%d")
        with patch("app.validate.hour_validator.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.strptime.side_effect = datetime.strptime
            with pytest.raises(PastHourSlotNotAllowedError):
                validate_hour_slots(["12:00", "13:00"], today)  # 연속 + 14:00 기준 과거

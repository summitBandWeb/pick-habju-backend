from datetime import datetime, timedelta
from datetime import datetime as dt_original
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
    _is_overnight,
    OVERNIGHT_LATE_START_MINUTES,
    OVERNIGHT_EARLY_END_MINUTES,
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
            mock_dt.strptime = dt_original.strptime  # side_effect 대신 직접 할당으로 호출 경로를 명확히 함
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
            mock_dt.strptime = dt_original.strptime  # side_effect 대신 직접 할당으로 호출 경로를 명확히 함
            with pytest.raises(PastHourSlotNotAllowedError):
                validate_hour_slots(["12:00", "13:00"], today)  # 연속 + 14:00 기준 과거

    @pytest.mark.parametrize("slots", [
        # [19:00 경계] 정확히 19:00부터 시작하는 overnight 5시간 예약 (end-inclusive 6슬롯)
        # NOTE: 05:00 경계 케이스는 19:00 이상→05:00 최소 10시간 거리라 5시간 제한 내 불가.
        #       05:00 경계는 _is_overnight() 단위테스트(TestIsOvernightUnit)에서 직접 검증.
        ["19:00", "20:00", "21:00", "22:00", "23:00", "00:00"],
    ])
    def test_overnight_boundary_slots_are_not_rejected(self, slots):
        """19:00·05:00 경계값이 포함된 연속 overnight 슬롯은 과거 판정 없이 통과해야 함

        Rationale:
            OVERNIGHT_LATE_START_MINUTES(19:00)·OVERNIGHT_EARLY_END_MINUTES(05:00) 상수를
            직접 검증하는 경계 테스트. 임계값이 변경되면 이 테스트가 즉시 실패하여 미탐지를 방지함.
            NOTE: 19:00 슬롯이 '미래'가 되도록 now를 18:00으로 고정. (22:00으로 하면 19:00이 과거 시간이 됨)
        """
        fixed_now = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        today = fixed_now.strftime("%Y-%m-%d")
        with patch("app.validate.hour_validator.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.strptime = dt_original.strptime  # side_effect 대신 직접 할당으로 호출 경로를 명확히 함
            # overnight으로 판별되어 새벽 슬롯이 과거 판정에서 제외 → 예외 없이 통과해야 함
            validate_hour_slots(slots, today)

    def test_overnight_exact_boundary_23_to_04(self):
        """23:00~04:00 (OVERNIGHT_EARLY_END_MINUTES = 04:00 정각 경계) overnight는 예외 없이 통과해야 함

        Rationale:
            최대 5시간 overnight의 가장 늦은 조합 '23:00 ~ 04:00'을 검증.
            OVERNIGHT_EARLY_END_MINUTES(04:00, 240분)가 <= 비교이므로
            04:00 슬롯(240분)이 overnight 새벽으로 판별되어 과거 검증에서 제외되어야 함.
            임계값(<=)을 < 로 잘못 변경하면 이 테스트가 즉시 실패하여 미탐지를 방지함.
            NOTE: 05:00(300분)은 OVERNIGHT_EARLY_END_MINUTES(240분) 초과라 overnight skip 대상이 아님.
                  19:00+05:00 조합은 10시간이므로 DTO 5시간 제한에도 위배됨. 해당 경계는
                  TestIsOvernightUnit.test_is_overnight_boundary에서 단위 검증함.
            NOTE: 23:00 슬롯이 미래가 되도록 now를 22:00으로 고정.
        """
        fixed_now = datetime.now().replace(hour=22, minute=0, second=0, microsecond=0)
        today = fixed_now.strftime("%Y-%m-%d")
        slots = ["23:00", "00:00", "01:00", "02:00", "03:00", "04:00"]  # 정확히 5시간
        with patch("app.validate.hour_validator.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.strptime = dt_original.strptime
            # 04:00이 overnight 새벽으로 판별되어 과거 검증 제외 → 예외 없이 통과
            validate_hour_slots(slots, today)

    def test_non_overnight_early_morning_past_rejected(self):
        """overnight이 아닌데 새벽 슬롯만 있는 경우 과거 시간으로 거부되어야 함

        Rationale:
            02:00, 03:00은 19:00 이상 슬롯이 없으므로 overnight 미해당.
            14:00 기준으로 02:00~03:00은 이미 과거이므로 PastHourSlotNotAllowedError 발생해야 함.
            overnight 스킵 로직이 일반 새벽 과거 슬롯을 잘못 통과시키지 않는지 회귀 방지.
        """
        fixed_now = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
        today = fixed_now.strftime("%Y-%m-%d")
        slots = ["02:00", "03:00"]  # 심야 슬롯 없음 → overnight 아님, 모두 과거
        with patch("app.validate.hour_validator.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.strptime = dt_original.strptime
            with pytest.raises(PastHourSlotNotAllowedError):
                validate_hour_slots(slots, today)


class TestIsOvernightUnit:
    """_is_overnight() 헬퍼 함수 단위 테스트 (경계값 중점)"""

    @pytest.mark.parametrize("minutes,expected", [
        # overnight O: 정확히 경계값 포함
        ([OVERNIGHT_LATE_START_MINUTES, 60], True),          # 19:00 + 01:00
        ([OVERNIGHT_EARLY_END_MINUTES, 1200], True),         # 새벽 경계(04:00)와 심야(20:00)가 공존 → overnight
        ([OVERNIGHT_LATE_START_MINUTES, OVERNIGHT_EARLY_END_MINUTES], True),  # 양쪽 경계
        ([1380, 60], True),                                  # 23:00 + 01:00
        # overnight X: 경계보다 1단위 미달/초과
        ([OVERNIGHT_LATE_START_MINUTES - 60, 60], False),    # 18:00(경계 미만) + 01:00
        ([1200, OVERNIGHT_EARLY_END_MINUTES + 60], False),   # 20:00 + 05:00(경계 초과)
        ([1200, 480], False),                                # 20:00만 있고 새벽 없음
        ([60, OVERNIGHT_EARLY_END_MINUTES], False),          # 01:00만 있고 심야 없음
    ])
    def test_is_overnight_boundary(self, minutes, expected):
        """_is_overnight()가 19:00/04:00 경계값을 포함(inclusive) 처리하는지 검증

        Rationale:
            OVERNIGHT_LATE_START_MINUTES·OVERNIGHT_EARLY_END_MINUTES 상수를 >= / <= 로
            비교하므로 경계값 자체도 overnight으로 판별되어야 함.
            이 테스트가 실패하면 상수 또는 비교 연산자가 잘못 변경된 것임.
        """
        assert _is_overnight(minutes) == expected

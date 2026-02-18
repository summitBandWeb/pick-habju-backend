from datetime import datetime, timedelta

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
    if now.hour == 0:
        slot = "23:00"
        today = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        slot = f"{(now.hour - 1):02d}:00"
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

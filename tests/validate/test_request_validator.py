from datetime import datetime, timedelta
from unittest.mock import patch

from app.validate.request_validator import validate_availability_request


def _future_date(days: int = 2) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def test_validate_availability_request_allows_empty_target_rooms():
    """빈 room list는 no-result 정상 시나리오로 허용해야 한다."""
    date = _future_date()
    hour_slots = ["18:00", "19:00"]

    with patch("app.validate.request_validator.validate_room_detail_list") as mock_validate:
        validate_availability_request(date=date, hour_slots=hour_slots, target_rooms=[])
        mock_validate.assert_not_called()


def test_validate_availability_request_validates_room_list_when_present():
    """room list가 존재하면 기존 room detail 검증을 수행해야 한다."""
    date = _future_date()
    hour_slots = ["18:00", "19:00"]

    with patch("app.validate.request_validator.validate_room_detail_list") as mock_validate:
        validate_availability_request(
            date=date,
            hour_slots=hour_slots,
            target_rooms=[object()],
        )
        mock_validate.assert_called_once()

from app.models.dto import AvailabilityRequest
from pydantic import ValidationError
import pytest

def test_coordinate_range_invalid_lat():
    """위도 범위(-90~90) 초과 테스트"""
    data = {
        "date": "2029-12-31",
        "capacity": 3,
        "start_hour": "14:00",
        "end_hour": "16:00",
        "swLat": -91.0, "swLng": 127.0, "neLat": 38.0, "neLng": 128.0
    }
    with pytest.raises(ValidationError) as excinfo:
        AvailabilityRequest(**data)
    assert "위도" in str(excinfo.value)

def test_coordinate_range_invalid_lng():
    """경도 범위(-180~180) 초과 테스트"""
    data = {
        "date": "2029-12-31",
        "capacity": 3,
        "start_hour": "14:00",
        "end_hour": "16:00",
        "swLat": 37.0, "swLng": -181.0, "neLat": 38.0, "neLng": 128.0
    }
    with pytest.raises(ValidationError) as excinfo:
        AvailabilityRequest(**data)
    assert "경도" in str(excinfo.value)

def test_coordinate_order_invalid():
    """좌표 정렬(SW < NE) 실패 테스트"""
    data = {
        "date": "2029-12-31",
        "capacity": 3,
        "start_hour": "14:00",
        "end_hour": "16:00",
        "swLat": 38.0, "swLng": 127.0, "neLat": 37.0, "neLng": 128.0
    }
    with pytest.raises(ValidationError) as excinfo:
        AvailabilityRequest(**data)
    assert "작아야 합니다" in str(excinfo.value)

def test_coordinate_success():
    """정상 좌표 통과 테스트"""
    data = {
        "date": "2029-12-31",
        "capacity": 3,
        "start_hour": "14:00",
        "end_hour": "16:00",
        "swLat": 37.0, "swLng": 127.0, "neLat": 37.5, "neLng": 127.5
    }
    req = AvailabilityRequest(**data)
    assert req.swLat == 37.0

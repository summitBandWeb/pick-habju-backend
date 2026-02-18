from app.models.dto import AvailabilityRequest
from pydantic import ValidationError
import pytest
from datetime import datetime, date

def test_date_calendar_validity():
    """달력상 유효하지 않은 날짜(예: 2월 30일) 검증 테스트"""
    data = {
        "date": "2024-02-30",
        "capacity": 3,
        "start_hour": "14:00",
        "end_hour": "16:00",
        "swLat": 37.0, "swLng": 127.0, "neLat": 38.0, "neLng": 128.0
    }
    
    with pytest.raises(ValidationError) as excinfo:
        AvailabilityRequest(**data)
    
    # 에러 메시지에 "날짜 형식" 또는 "올바르지 않습니다" 포함 확인
    assert "날짜 형식" in str(excinfo.value)

def test_date_past_validity():
    """과거 날짜 검증 테스트"""
    data = {
        "date": "2020-01-01",
        "capacity": 3,
        "start_hour": "14:00",
        "end_hour": "16:00",
        "swLat": 37.0, "swLng": 127.0, "neLat": 38.0, "neLng": 128.0
    }
    
    with pytest.raises(ValidationError) as excinfo:
        AvailabilityRequest(**data)
    
    assert "과거 날짜" in str(excinfo.value)

def test_date_success():
    """정상 날짜 통과 테스트"""
    # 미래의 날짜 사용
    future_date = "2029-12-31"
    data = {
        "date": future_date,
        "capacity": 3,
        "start_hour": "14:00",
        "end_hour": "16:00",
        "swLat": 37.0, "swLng": 127.0, "neLat": 38.0, "neLng": 128.0
    }
    
    req = AvailabilityRequest(**data)
    assert req.date == future_date

if __name__ == "__main__":
    # 직접 실행 시 pytest로 실행
    pytest.main([__file__])

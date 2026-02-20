from fastapi.testclient import TestClient
from app.main import app
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

client = TestClient(app)

def test_availability_request_validation_error():
    """AvailabilityRequest DTO 검증 실패 시 422 에러 반환 테스트"""
    url = "/api/rooms/availability"
    
    # 1. Invalid Date Format (YYYY/MM/DD)
    response = client.get(f"{url}?date=2024/01/01&capacity=3&start_hour=18:00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
    assert response.status_code == 422
    assert "date" in response.text
    
    # 2. Invalid Time Format (HH-MM)
    response = client.get(f"{url}?date=2024-01-01&capacity=3&start_hour=18-00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
    assert response.status_code == 422
    assert "start_hour" in response.text

    # 3. Invalid Time Range (25:00)
    response = client.get(f"{url}?date=2024-01-01&capacity=3&start_hour=25:00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
    assert response.status_code == 422
    assert "start_hour" in response.text

    # 4. Invalid Capacity (0)
    response = client.get(f"{url}?date=2024-01-01&capacity=0&start_hour=18:00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
    assert response.status_code == 422
    assert "capacity" in response.text

    # 5. Invalid Capacity (101 - Exceeds 100)
    response = client.get(f"{url}?date=2024-01-01&capacity=101&start_hour=18:00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
    assert response.status_code == 422
    assert "capacity" in response.text

    # 6. Past Date (Logic Check)    
    # Deterministic base time: Jan 1st, 2025 at 12:00 PM (Midday)
    now = datetime(2025, 1, 1, 12, 0)
    today_str = now.strftime("%Y-%m-%d")
    
    with patch('app.models.dto.date') as mock_date, \
         patch('app.models.dto.datetime') as mock_datetime:
        
        mock_date.today.return_value = now.date()
        mock_datetime.now.return_value = now
        # datetime.strptime은 실제 함수를 사용하도록 설정
        mock_datetime.strptime.side_effect = datetime.strptime
        
        # 6. Past Date
        past_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        response = client.get(f"{url}?date={past_date}&capacity=3&start_hour=18:00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
        assert response.status_code == 422
        assert "date" in response.text or "과거 날짜" in response.text

        # 7. Start > End Time (Logic Check)
        future_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        response = client.get(f"{url}?date={future_date}&capacity=3&start_hour=21:00&end_hour=18:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
        assert response.status_code == 422
        assert "start_hour" in response.text or "end_hour" in response.text or "시작 시간" in response.text

        # 9. Past Time (Today)
        # 현재 시간(12:00)보다 1시간 전으로 요청 (11:00)
        past_hour = (now - timedelta(hours=1)).strftime("%H:%M")
        # end_hour는 14:00
        end_hour = (now + timedelta(hours=2)).strftime("%H:%M")
        
        response = client.get(f"{url}?date={today_str}&capacity=3&start_hour={past_hour}&end_hour={end_hour}&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
        assert response.status_code == 422
        assert "지나간 시간" in response.text or "past" in response.text.lower()

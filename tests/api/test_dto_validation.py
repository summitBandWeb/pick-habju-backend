from fastapi.testclient import TestClient
from app.main import app
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.core.limiter import limiter
from app.models.dto import AvailabilityRequest

@pytest.fixture(autouse=True)
def disable_limiter():
    """Rate Limiter 비활성화 (검증 로직 테스트에서 429 방지)"""
    limiter.enabled = False
    yield
    limiter.enabled = True

client = TestClient(app)

def test_availability_request_validation_error():
    """AvailabilityRequest DTO 검증 실패 시 422 에러 반환 테스트"""
    url = "/api/rooms/availability"
    
    # Invalid Date Format (YYYY/MM/DD)
    response = client.get(f"{url}?date=2024/01/01&capacity=3&start_hour=18:00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
    assert response.status_code == 422
    assert "date" in response.text
    
    # Invalid Time Format (HH-MM)
    response = client.get(f"{url}?date=2024-01-01&capacity=3&start_hour=18-00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
    assert response.status_code == 422
    assert "start_hour" in response.text

    # Invalid Time Range (25:00)
    response = client.get(f"{url}?date=2024-01-01&capacity=3&start_hour=25:00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
    assert response.status_code == 422
    assert "start_hour" in response.text

    # Invalid Capacity (0)
    response = client.get(f"{url}?date=2024-01-01&capacity=0&start_hour=18:00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
    assert response.status_code == 422
    assert "capacity" in response.text

    # Invalid Capacity (101 - Exceeds 100)
    response = client.get(f"{url}?date=2024-01-01&capacity=101&start_hour=18:00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
    assert response.status_code == 422
    assert "capacity" in response.text

    # Past Date (Logic Check)    
    # Deterministic base time: Jan 1st, 2025 at 12:00 PM (Midday)
    now = datetime(2025, 1, 1, 12, 0)
    today_str = now.strftime("%Y-%m-%d")
    
    with patch('app.models.dto.date') as mock_date, \
         patch('app.models.dto.datetime') as mock_datetime:
        
        mock_date.today.return_value = now.date()
        mock_datetime.now.return_value = now
        # datetime.strptime은 실제 함수를 사용하도록 설정
        mock_datetime.strptime.side_effect = datetime.strptime
        
        # Past Date
        past_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        response = client.get(f"{url}?date={past_date}&capacity=3&start_hour=18:00&end_hour=21:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
        assert response.status_code == 422
        assert "date" in response.text or "과거 날짜" in response.text
        
        # NOTE: 아래 케이스부터는 로직 그룹화 및 유지보수 편의를 위해 개별 번호(Case 7 이후)를 생략합니다.

        # Start > End Time (Logic Check) -> This now falls into the > 5 hours check
        future_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        response = client.get(f"{url}?date={future_date}&capacity=3&start_hour=21:00&end_hour=18:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
        assert response.status_code == 422
        assert "5시간" in response.text

        # Past Time (Today)
        # 현재 시간(12:00)보다 1시간 전으로 요청 (11:00)
        past_hour = (now - timedelta(hours=1)).strftime("%H:%M")
        # end_hour는 14:00
        end_hour = (now + timedelta(hours=2)).strftime("%H:%M")
        
        response = client.get(f"{url}?date={today_str}&capacity=3&start_hour={past_hour}&end_hour={end_hour}&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
        assert response.status_code == 422
        assert "지나간 시간" in response.text or "past" in response.text.lower()

        # Valid Overnight (23:00 ~ 02:00) -> 3 hours, should PASS validation
        # Note: Using app.dependency_overrides to mock the service for a clean test
        from app.api.dependencies import get_availability_service
        
        async def mock_check_availability(*args, **kwargs):
            return {
                "date": future_date,
                "start_hour": "23:00",
                "end_hour": "02:00",
                "hour_slots": ["23:00", "00:00", "01:00", "02:00"],
                "available_biz_item_ids": [],
                "branches": []
            }

        with patch('app.api.available_room.get_availability_service') as mock_get_svc:
            mock_svc = mock_get_svc.return_value
            mock_svc.check_availability = mock_check_availability
            app.dependency_overrides[get_availability_service] = lambda: mock_svc

            try:
                response = client.get(f"{url}?date={future_date}&capacity=3&start_hour=23:00&end_hour=02:00&swLat=37.0&swLng=127.0&neLat=38.0&neLng=128.0")
                assert response.status_code == 200
                assert response.json()["isSuccess"] is True
            finally:
                app.dependency_overrides.clear()

def test_dto_logic_boundary_cases():
    """AvailabilityRequest DTO 자체의 비즈니스 로직(경계값) 단위 테스트"""
    
    # 공통 파라미터 (미래 날짜 사용으로 과거 날짜 검증 회피)
    base_params = {
        "date": "2099-01-01",
        "capacity": 3,
        "swLat": 37.0, "swLng": 127.0, "neLat": 38.0, "neLng": 128.0
    }

    # 1. 경계값: 정확히 5시간 (00:00 ~ 05:00) -> 통과
    req = AvailabilityRequest(start_hour="00:00", end_hour="05:00", **base_params)
    assert req.validate_logic() is not None

    # 2. 경계값: 5시간 1분 초과 (00:00 ~ 05:01) -> FAIL
    with pytest.raises(ValueError, match="5시간"):
        AvailabilityRequest(start_hour="00:00", end_hour="05:01", **base_params).validate_logic()

    # 3. 0시간 예약 (14:00 ~ 14:00) -> FAIL
    with pytest.raises(ValueError, match="같을 수 없습니다"):
        AvailabilityRequest(start_hour="14:00", end_hour="14:00", **base_params).validate_logic()
    
    # 4. 심야 예약 (23:00 ~ 02:00) -> 통과 (3시간)
    req = AvailabilityRequest(start_hour="23:00", end_hour="02:00", **base_params)
    assert req.validate_logic() is not None

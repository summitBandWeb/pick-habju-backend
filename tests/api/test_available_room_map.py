import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
from app.models.dto import AvailabilityRequest
from datetime import datetime, timedelta

@pytest.fixture
def future_date():
    return (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

@pytest.mark.asyncio
async def test_map_search_validation_error(async_client: AsyncClient, future_date):
    """
    [검증 로직 테스트]
    잘못된 좌표 범위(남서쪽이 북동쪽보다 큰 경우)로 요청 시 400 에러가 반환되어야 한다.
    """
    # given
    params = {
        "date": future_date,
        "capacity": 3,
        "start_hour": "12:00",
        "end_hour": "14:00",
        "swLat": 37.5, # 남서쪽 위도가
        "neLat": 37.0, # 북동쪽 위도보다 큼 (Error Case)
        "swLng": 127.0,
        "neLng": 127.1
    }

    # when
    response = await async_client.get("/api/rooms/availability", params=params)

    # then
    assert response.status_code == 400
    assert "남서쪽 위도(swLat)는 북동쪽 위도(neLat)보다 작아야 합니다" in response.json()['message']


@pytest.mark.asyncio
async def test_map_search_coordinate_range_error(async_client: AsyncClient, future_date):
    """
    [검증 로직 테스트]
    위도 범위를 벗어난 값(91도) 요청 시 400 에러가 반환되어야 한다.
    """
    # given
    params = {
        "date": future_date,
        "capacity": 3,
        "start_hour": "12:00",
        "end_hour": "14:00",
        "swLat": 91.0, # 유효 범위 초과
        "neLat": 37.6, 
        "swLng": 127.0,
        "neLng": 127.1
    }

    # when
    response = await async_client.get("/api/rooms/availability", params=params)

    # then
    assert response.status_code == 400
    assert "위도는 -90도에서 90도 사이여야 합니다" in response.json()['message']


@pytest.mark.asyncio
async def test_map_search_success(
    async_client: AsyncClient,
    mock_availability_response_factory, 
    mock_room_info_factory,
    mock_branch_stats_factory,
    future_date
):
    """
    [통합 시나리오 테스트]
    정상적인 좌표 범위 요청 시, 서비스 레이어의 결과가 API 응답 스펙에 맞게 반환되어야 한다.
    기존 구조(room_detail 중첩) + branch_summary 포함.
    """
    # given
    # 기존 RoomAvailability 구조에 맞게 Mock 생성
    room_avail = mock_room_info_factory(name="Refactored Room", price=20000)
    branch_stats = mock_branch_stats_factory(min_price=20000)
    
    # Mock 응답 생성
    mock_response = mock_availability_response_factory(
        results=[room_avail],
        summary={"12345": branch_stats}
    )

    with patch("app.services.availability_service.AvailabilityService.check_availability", new_callable=AsyncMock) as mock_method:
        mock_method.return_value = mock_response

        params = {
            "date": future_date,
            "capacity": 5,
            "start_hour": "12:00",
            "end_hour": "14:00",
            "swLat": 37.4,
            "neLat": 37.6,
            "swLng": 126.9,
            "neLng": 127.1
        }

        # when
        response = await async_client.get("/api/rooms/availability", params=params)

        # then
        assert response.status_code == 200
        data = response.json()["result"]
        
        # 기존 구조 검증 (room_detail 중첩)
        assert "branch_summary" in data
        assert "hour_slots" in data
        assert data["results"][0]["room_detail"]["name"] == "Refactored Room"
        
        # Mock 호출 파라미터 검증
        called_arg = mock_method.call_args[1]['request']
        assert isinstance(called_arg, AvailabilityRequest)
        assert called_arg.neLat == 37.6

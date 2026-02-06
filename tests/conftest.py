import pytest
from app.models.dto import RoomDetail, RoomAvailability, BranchStats, AvailabilityResponse
from httpx import AsyncClient, ASGITransport
from app.main import app

import pytest_asyncio

@pytest_asyncio.fixture
async def async_client():
    """ FastAPI 앱을 위한 AsyncClient Fixture """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest.fixture
def mock_room_detail_factory():
    """ RoomDetail 객체를 동적으로 생성하는 Factory Fixture """
    def _create(
        name="Test Room",
        branch="Test Branch",
        business_id="12345",
        biz_item_id="67890",
        price=15000,
        lat=37.5,
        lng=127.0,
        **kwargs
    ):
        defaults = {
            "name": name,
            "branch": branch,
            "business_id": business_id,
            "biz_item_id": biz_item_id,
            "imageUrls": ["http://test.com/img.jpg"],
            "maxCapacity": 10,
            "recommendCapacity": 5,
            "baseCapacity": None,
            "extraCharge": None,
            "pricePerHour": price,
            "canReserveOneHour": True,
            "requiresCallOnSameDay": False,
            "lat": lat,
            "lng": lng
        }
        defaults.update(kwargs)
        return RoomDetail(**defaults)
    return _create

@pytest.fixture
def mock_room_info_factory(mock_room_detail_factory):
    """ RoomAvailability 객체를 동적으로 생성하는 Factory Fixture (기존 구조 유지) """
    def _create(name="Test Room", price=15000, available=True, **kwargs):
        room_detail = mock_room_detail_factory(name=name, price=price, **kwargs)
        return RoomAvailability(
            room_detail=room_detail,
            available=available,
            available_slots={"12:00": True, "13:00": True}
        )
    return _create

@pytest.fixture
def mock_branch_stats_factory():
    """ BranchStats 객체 Factory """
    def _create(min_price=15000, count=1, lat=37.5, lng=127.0):
        return BranchStats(
            min_price=min_price,
            available_count=count,
            lat=lat,
            lng=lng
        )
    return _create

@pytest.fixture
def mock_availability_response_factory(mock_room_info_factory, mock_branch_stats_factory):
    """ AvailabilityResponse 객체 Factory (기존 구조 + branch_summary) """
    def _create(results=None, summary=None):
        if results is None:
            results = [mock_room_info_factory()]
        if summary is None:
            summary = {"12345": mock_branch_stats_factory()}
            
        return AvailabilityResponse(
            date="2024-05-01",
            start_hour="12:00",
            end_hour="14:00",
            hour_slots=["12:00", "13:00", "14:00"],
            available_biz_item_ids=["67890"],
            results=results,
            branch_summary=summary
        )
    return _create

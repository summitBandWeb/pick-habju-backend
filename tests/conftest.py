import pytest
from app.models.dto import RoomDetail, RoomAvailability, AvailabilityResponse
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models.dto import BranchResponse

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
            "image_urls": ["http://test.com/img.jpg"],
            "max_capacity": 10,
            "recommend_capacity_range": [3, 5],
            "base_capacity": None,
            "extra_charge": None,
            "price_per_hour": price,
            "can_reserve_one_hour": True,
            "requires_contact_on_sameday": False,
            "lat": lat,
            "lng": lng
        }
        defaults.update(kwargs)
        return RoomDetail(**defaults)
    return _create

@pytest.fixture
def mock_room_response_factory():
    """ RoomResponse 객체를 동적으로 생성하는 Factory Fixture """
    def _create(name="Test Room", price=15000, available=True, **kwargs):
        from app.models.dto import RoomResponse
        defaults = {
            "biz_item_id": "67890",
            "name": name,
            "price_per_hour": price,
            "available": available,
            "available_slots": {"12:00": True, "13:00": True},
            "estimated_price": price,
            "image_urls": ["http://test.com/img.jpg"],
            "max_capacity": 10,
            "recommend_capacity": 5,
            "min_capacity": 1,
            "min_hours": 1,
            "standby_days": None,
            "policy_warnings": []
        }
        defaults.update(kwargs)
        return RoomResponse(**defaults)
    return _create

@pytest.fixture
def mock_branch_response_factory(mock_room_response_factory):
    """ BranchResponse 객체 Factory """
    def _create(business_id="12345", branch="Test Branch", min_price_available=None, min_price_partial=None, count=None, lat=37.5, lng=127.0, rooms=None, **kwargs):
        from app.models.dto import BranchResponse
        if rooms is None:
            # 기본적으로 방 하나를 생성. 가격은 available 또는 partial 중 있는 값을 사용.
            price = min_price_available if min_price_available is not None else min_price_partial if min_price_partial is not None else 15000
            rooms = [mock_room_response_factory(price=price)]
        
        if count is None:
            count = len(rooms)
        defaults = {
            "business_id": business_id,
            "branch": branch,
            "min_price_available": min_price_available,
            "min_price_partial": min_price_partial,
            "available_count": count,
            "lat": lat,
            "lng": lng,
            "rooms": rooms
        }
        defaults.update(kwargs)
        return BranchResponse(**defaults)
    return _create

@pytest.fixture
def mock_availability_response_factory(mock_branch_response_factory):
    """ AvailabilityResponse 객체 Factory (branches nested structure) """
    def _create(branches=None):
        if branches is None:
            branches = [mock_branch_response_factory()]
            
        return AvailabilityResponse(
            date="2024-05-01",
            start_hour="12:00",
            end_hour="14:00",
            hour_slots=["12:00", "13:00", "14:00"],
            available_biz_item_ids=["67890"],
            branches=branches
        )
    return _create

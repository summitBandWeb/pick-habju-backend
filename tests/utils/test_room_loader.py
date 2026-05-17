import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.utils import room_loader


def _room_row(**overrides):
    row = {
        "name": "A room",
        "business_id": "522011",
        "biz_item_id": "item-1",
        "image_urls": [],
        "max_capacity": 5,
        "recommend_capacity": 4,
        "price_config": None,
        "price_per_hour": 10000,
        "can_reserve_one_hour": True,
        "requires_call_on_sameday": False,
    }
    row.update(overrides)
    return row


def _mock_supabase(data: list):
    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.gte.return_value = mock_query
    mock_query.lte.return_value = mock_query
    mock_query.execute = AsyncMock(return_value=SimpleNamespace(data=data))

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = mock_query
    return mock_supabase, mock_query


@pytest.mark.asyncio
async def test_get_rooms_by_criteria_filters_by_service_area(monkeypatch):
    # 서비스 지역 밖 (부산 근처) -> 제외
    out_of_area_row = _room_row(
        name="B room",
        biz_item_id="item-2",
        branch={"name": "Busan", "lat": 35.0, "lng": 129.0},
    )
    # 서비스 지역 안 (홍대입구역 근처) -> 포함
    in_area_row = _room_row(
        name="C room",
        biz_item_id="item-3",
        branch={"name": "Hongdae", "lat": 37.556, "lng": 126.924},
    )

    mock_supabase, mock_query = _mock_supabase([out_of_area_row, in_area_row])
    monkeypatch.setattr(room_loader, "get_async_supabase_client", AsyncMock(return_value=mock_supabase))

    rooms = await room_loader.get_rooms_by_criteria(
        capacity=3, swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
    )

    assert any(call.args and "branch!inner(" in call.args[0] for call in mock_query.select.call_args_list)
    assert mock_query.gte.call_count >= 2
    assert mock_query.lte.call_count >= 2

    gte_args = [call.args[0] for call in mock_query.gte.call_args_list]
    assert "branch.lat" in gte_args
    assert "branch.lng" in gte_args

    assert len(rooms) == 1
    assert rooms[0].biz_item_id == "item-3"


@pytest.mark.asyncio
async def test_get_rooms_by_criteria_returns_service_area_room(monkeypatch):
    row = _room_row(branch={"name": "Branch", "lat": 37.477, "lng": 126.982})

    mock_supabase, _ = _mock_supabase([row])
    monkeypatch.setattr(room_loader, "get_async_supabase_client", AsyncMock(return_value=mock_supabase))

    rooms = await room_loader.get_rooms_by_criteria(capacity=1)

    assert len(rooms) == 1


@pytest.mark.asyncio
async def test_get_rooms_by_criteria_boundary_coordinates(monkeypatch):
    """경계값 테스트: swLat, swLng, neLat, neLng 경계선에 위치한 지점 포함 검증"""
    sw_edge_row = _room_row(
        biz_item_id="item-sw",
        branch={"name": "Sadang", "lat": 37.4766, "lng": 126.9816},
    )
    ne_edge_row = _room_row(
        biz_item_id="item-ne",
        branch={"name": "Isu", "lat": 37.4856, "lng": 126.9823},
    )
    outside_row = _room_row(
        biz_item_id="item-out",
        branch={"name": "Out Branch", "lat": 37.4765, "lng": 126.9815},
    )

    mock_supabase, _ = _mock_supabase([sw_edge_row, ne_edge_row, outside_row])
    monkeypatch.setattr(room_loader, "get_async_supabase_client", AsyncMock(return_value=mock_supabase))
    monkeypatch.setattr(room_loader, "is_in_service_area", lambda lat, lng: True)

    rooms = await room_loader.get_rooms_by_criteria(
        capacity=1,
        swLat=37.4766, swLng=126.9816,
        neLat=37.4856, neLng=126.9823,
    )

    assert len(rooms) == 2
    assert {r.biz_item_id for r in rooms} == {"item-sw", "item-ne"}

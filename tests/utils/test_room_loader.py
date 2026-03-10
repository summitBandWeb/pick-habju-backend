from types import SimpleNamespace
from unittest.mock import MagicMock

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


def test_get_rooms_by_criteria_filters_by_service_area(monkeypatch):
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

    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.gte.return_value = mock_query
    mock_query.execute.return_value = SimpleNamespace(
        data=[out_of_area_row, in_area_row]
    )

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = mock_query
    monkeypatch.setattr(room_loader, "supabase", mock_supabase)

    rooms = room_loader.get_rooms_by_criteria(
        capacity=3, swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0
    )

    assert len(rooms) == 1
    assert rooms[0].biz_item_id == "item-3"


def test_get_rooms_by_criteria_returns_service_area_room(monkeypatch):
    # 서비스 지역 안 (사당역 근처)
    row = _room_row(branch={"name": "Branch", "lat": 37.477, "lng": 126.982})

    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.gte.return_value = mock_query
    mock_query.execute.return_value = SimpleNamespace(data=[row])

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = mock_query
    monkeypatch.setattr(room_loader, "supabase", mock_supabase)

    rooms = room_loader.get_rooms_by_criteria(capacity=1)

    assert len(rooms) == 1

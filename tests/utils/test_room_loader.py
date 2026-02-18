from types import SimpleNamespace
from unittest.mock import MagicMock

from app.utils import room_loader


def _room_row(**overrides):
    row = {
        "name": "A룸",
        "business_id": "biz-1",
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


def test_get_rooms_by_criteria_keeps_room_when_branch_missing(monkeypatch):
    missing_branch_row = _room_row(branch=None, image_urls=None)
    out_of_bound_row = _room_row(
        name="B룸",
        biz_item_id="item-2",
        branch={"name": "강남점", "lat": 35.0, "lng": 129.0},
    )
    in_bound_row = _room_row(
        name="C룸",
        biz_item_id="item-3",
        branch={"name": "홍대점", "lat": 37.5, "lng": 127.1},
    )

    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.gte.return_value = mock_query
    mock_query.execute.return_value = SimpleNamespace(
        data=[missing_branch_row, out_of_bound_row, in_bound_row]
    )

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = mock_query
    monkeypatch.setattr(room_loader, "supabase", mock_supabase)

    rooms = room_loader.get_rooms_by_criteria(
        capacity=3, swLat=37.0, swLng=127.0, neLat=38.0, neLng=128.0
    )

    assert len(rooms) == 2
    assert {r.biz_item_id for r in rooms} == {"item-1", "item-3"}
    missing_branch = [r for r in rooms if r.biz_item_id == "item-1"][0]
    assert missing_branch.branch == "지점 정보 없음"

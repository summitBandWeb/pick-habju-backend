from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_supabase():
    mock = MagicMock()

    mock_room_table = MagicMock()
    mock_room_table.upsert.return_value.execute.return_value = MagicMock()
    mock_room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    mock_branch_table = MagicMock()
    mock_branch_table.upsert.return_value.execute.return_value = MagicMock()

    def table_dispatcher(name):
        tables = {
            "room": mock_room_table,
            "branch": mock_branch_table,
        }
        if name not in tables:
            raise AssertionError(f"Unexpected table access in test: {name}")
        return tables[name]

    mock.table.side_effect = table_dispatcher
    mock._room_table = mock_room_table
    mock._branch_table = mock_branch_table
    return mock


@pytest.fixture
def service(mock_supabase):
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client", return_value=mock_supabase
    ):
        from app.services.room_collection_service import RoomCollectionService

        svc = RoomCollectionService()
        svc.supabase = mock_supabase
        return svc


@pytest.mark.asyncio
async def test_price_inference_applied_when_parser_has_no_capacity(service, mock_supabase):
    business = {
        "businessId": "917236",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Classic",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 20000},
        }
    ]
    parsed_results = {"room1": {"max_capacity": None, "recommend_capacity": None}}

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["max_capacity"] == 12
    assert room_data["recommend_capacity"] == 6
    assert room_data["recommend_capacity_range"] == [4, 6]


@pytest.mark.asyncio
async def test_price_inference_skipped_when_parser_already_has_capacity(service, mock_supabase):
    business = {
        "businessId": "917236",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Classic",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 20000},
        }
    ]
    parsed_results = {
        "room1": {
            "max_capacity": 9,
            "recommend_capacity": 5,
            "recommend_capacity_range": [4, 5],
        }
    }

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["max_capacity"] == 9
    assert room_data["recommend_capacity"] == 5
    assert room_data["recommend_capacity_range"] == [4, 5]


@pytest.mark.asyncio
async def test_price_inference_uses_tolerance_window(service, mock_supabase):
    business = {
        "businessId": "1384809",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "R룸",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 14500},
        }
    ]
    parsed_results = {"room1": {"max_capacity": None, "recommend_capacity": None}}

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["max_capacity"] == 10
    assert room_data["recommend_capacity"] == 5
    assert room_data["recommend_capacity_range"] == [3, 5]

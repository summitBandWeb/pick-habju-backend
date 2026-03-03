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
    mock_branch_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    def table_dispatcher(name):
        if name == "room":
            return mock_room_table
        if name == "branch":
            return mock_branch_table
        return MagicMock()

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
async def test_save_to_db_replaces_room_like_branch_name_with_source_hint(service, mock_supabase):
    business = {"businessId": "biz1", "businessDisplayName": "A룸", "name": "A룸", "coordinates": None}
    rooms = [{"bizItemId": "r1", "name": "A룸", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
    parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}
    source_hint = {"id": "biz1", "name": "비쥬 합주실 1호점"}

    await service._save_to_db(business, rooms, parsed_results, source_hint=source_hint)

    upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
    branch_data = upsert_call[0][0]
    assert branch_data["name"] == "비쥬 합주실 1호점"
    assert branch_data["display_name"] == "비쥬 합주실 1호점"


@pytest.mark.asyncio
async def test_save_to_db_keeps_existing_branch_name_when_all_candidates_collide(service, mock_supabase):
    mock_supabase._branch_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"name": "기존 사당 합주실점", "display_name": "기존 사당 합주실점"}]
    )
    business = {"businessId": "biz1", "businessDisplayName": "A룸", "name": "A룸", "coordinates": None}
    rooms = [
        {"bizItemId": "r1", "name": "A룸", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}},
        {"bizItemId": "r2", "name": "S룸", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}},
    ]
    parsed_results = {
        "r1": {"max_capacity": 4, "recommend_capacity": 2},
        "r2": {"max_capacity": 4, "recommend_capacity": 2},
    }
    source_hint = {"id": "biz1", "name": "S룸"}

    await service._save_to_db(business, rooms, parsed_results, source_hint=source_hint)

    upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
    branch_data = upsert_call[0][0]
    assert branch_data["name"] == "기존 사당 합주실점"
    assert branch_data["display_name"] == "기존 사당 합주실점"


@pytest.mark.asyncio
async def test_save_to_db_falls_back_to_business_id_when_no_safe_branch_name(service, mock_supabase):
    business = {"businessId": "biz1", "businessDisplayName": "A룸", "name": "A룸", "coordinates": None}
    rooms = [{"bizItemId": "r1", "name": "A룸", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
    parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}
    source_hint = {"id": "biz1", "name": "A룸"}

    await service._save_to_db(business, rooms, parsed_results, source_hint=source_hint)

    upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
    branch_data = upsert_call[0][0]
    assert branch_data["name"] == "biz1"
    assert branch_data["display_name"] == "biz1"

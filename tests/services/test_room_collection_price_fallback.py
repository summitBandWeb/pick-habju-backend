import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_supabase():
    mock = MagicMock()

    mock_room_table = MagicMock()
    mock_room_table.upsert.return_value.execute.return_value = MagicMock()
    mock_room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    mock_branch_table = MagicMock()
    mock_branch_table.upsert.return_value.execute.return_value = MagicMock()

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
        "app.services.room_collection_service.get_supabase_client",
        return_value=mock_supabase,
    ):
        from app.services.room_collection_service import RoomCollectionService

        svc = RoomCollectionService()
        svc.supabase = mock_supabase
        return svc


def test_extract_price_fallback_from_price_field(service):
    room = {"minMaxPrice": None, "price": "18000"}
    assert service._extract_price(room) == 18000


def test_extract_price_fallback_from_room_name_text(service):
    room = {"name": "brown room (18,000 KRW / 1h)", "minMaxPrice": None}
    assert service._extract_price(room) == 18000


@pytest.mark.asyncio
async def test_save_to_db_skips_room_when_price_is_zero(service, mock_supabase):
    """price=0 룸은 유효한 예약 정보가 없으므로 저장하지 않는다."""
    business = {"businessId": "biz1", "businessDisplayName": "test studio"}
    rooms = [
        {
            "bizItemId": "room1",
            "name": "room-without-price",
            "bizItemResources": [],
            "minMaxPrice": None,
        }
    ]
    parsed_results = {"room1": {"max_capacity": 5, "recommend_capacity": 4}}

    await service._save_to_db(business, rooms, parsed_results)

    # price=0 룸은 upsert되지 않아야 한다 (branch upsert만 호출됨)
    room_upsert_calls = mock_supabase._room_table.upsert.call_args_list
    assert len(room_upsert_calls) == 0

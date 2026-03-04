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
async def test_save_to_db_uses_business_id_as_default_name_when_no_safe_branch_name(service, mock_supabase):
    # 왜: 모든 후보가 충돌하면 마지막 안전 fallback인 business_id를 강제해 오염된 branch명을 막아야 한다.
    # 사용처: _save_to_db(입력: business/rooms/parsed_results/source_hint) 호출 후 branch upsert payload 기본값을 검증한다.
    business = {"businessId": "biz1", "businessDisplayName": "A룸", "name": "A룸", "coordinates": None}
    rooms = [{"bizItemId": "r1", "name": "A룸", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
    parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}
    source_hint = {"id": "biz1", "name": "A룸"}

    await service._save_to_db(business, rooms, parsed_results, source_hint=source_hint)

    upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
    branch_data = upsert_call[0][0]
    assert branch_data["name"] == "biz1"
    assert branch_data["display_name"] == "biz1"


@pytest.mark.asyncio
async def test_save_to_db_uses_business_display_name_when_source_hint_is_missing(service, mock_supabase):
    business = {"businessId": "biz1", "businessDisplayName": "A룸 합주실", "name": "A룸 합주실", "coordinates": None}
    rooms = [{"bizItemId": "r1", "name": "B룸", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
    parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}
    
    await service._save_to_db(business, rooms, parsed_results, source_hint=None)

    upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
    branch_data = upsert_call[0][0]
    assert branch_data["name"] == "A룸 합주실"
    assert branch_data["display_name"] == "A룸 합주실"


@pytest.mark.asyncio
async def test_save_to_db_uses_business_name_when_prior_candidates_collide(service, mock_supabase):
    business = {"businessId": "biz1", "businessDisplayName": "A룸", "name": "안전한 합주실", "coordinates": None}
    rooms = [{"bizItemId": "r1", "name": "A룸", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
    parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}
    source_hint = {"id": "biz1", "name": "A룸"}
    
    await service._save_to_db(business, rooms, parsed_results, source_hint=source_hint)

    upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
    branch_data = upsert_call[0][0]
    assert branch_data["name"] == "안전한 합주실"
    assert branch_data["display_name"] == "안전한 합주실"


@pytest.mark.asyncio
async def test_save_to_db_keeps_branch_name_when_partially_overlaps_room_name(service, mock_supabase):
    business = {"businessId": "biz1", "businessDisplayName": "A룸 합주실", "name": "A룸 합주실", "coordinates": None}
    rooms = [{"bizItemId": "r1", "name": "A룸", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
    parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}
    source_hint = {"id": "biz1", "name": "A룸 합주실"}

    await service._save_to_db(business, rooms, parsed_results, source_hint=source_hint)

    upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
    branch_data = upsert_call[0][0]
    assert branch_data["name"] == "A룸 합주실"
    assert branch_data["display_name"] == "A룸 합주실"


@pytest.mark.asyncio
async def test_save_to_db_prefers_source_hint_when_both_hint_and_business_name_are_safe(service, mock_supabase):
    business = {"businessId": "biz1", "businessDisplayName": "원본 합주실", "name": "원본 합주실", "coordinates": None}
    rooms = [{"bizItemId": "r1", "name": "A룸", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
    parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}
    source_hint = {"id": "biz1", "name": "검색된 합주실"}

    await service._save_to_db(business, rooms, parsed_results, source_hint=source_hint)

    upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
    branch_data = upsert_call[0][0]
    assert branch_data["name"] == "검색된 합주실"
    assert branch_data["display_name"] == "검색된 합주실"


@pytest.mark.asyncio
async def test_save_to_db_detects_normalized_collision(service, mock_supabase):
    business = {"businessId": "biz1", "businessDisplayName": "A 룸", "name": "A 룸", "coordinates": None}
    rooms = [{"bizItemId": "r1", "name": "A룸", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
    parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}
    source_hint = {"id": "biz1", "name": "A 룸"}

    await service._save_to_db(business, rooms, parsed_results, source_hint=source_hint)

    upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
    branch_data = upsert_call[0][0]
    assert branch_data["name"] == "biz1"  # Collided with normalized room name "A룸" -> fallback to biz1
    assert branch_data["display_name"] == "biz1"

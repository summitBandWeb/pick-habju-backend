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
async def test_structured_min_booking_time_overrides_parser_can_reserve(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Room A",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": "RT01",
            "minBookingTime": 2,
            "extraFeeSettingJson": {},
        }
    ]
    parsed_results = {"room1": {"max_capacity": 6, "recommend_capacity": 4, "can_reserve_one_hour": True}}

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["can_reserve_one_hour"] is False


@pytest.mark.asyncio
async def test_parsed_can_reserve_used_when_structured_missing(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Room A",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": None,
            "minBookingTime": None,
            "bookingCountSettingJson": {},
            "extraFeeSettingJson": {},
        }
    ]
    parsed_results = {"room1": {"max_capacity": 6, "recommend_capacity": 4, "can_reserve_one_hour": False}}

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["can_reserve_one_hour"] is False


@pytest.mark.asyncio
async def test_structured_booking_count_json_string_overrides_parser(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Room A",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": "RT01",
            "bookingCountSettingJson": '{"minBookingTime": 2}',
            "extraFeeSettingJson": {},
        }
    ]
    parsed_results = {"room1": {"max_capacity": 6, "recommend_capacity": 4, "can_reserve_one_hour": True}}

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["can_reserve_one_hour"] is False


@pytest.mark.asyncio
async def test_structured_extra_charge_used_when_parser_missing(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Room A",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": "RT01",
            "minBookingTime": 1,
            "extraFeeSettingJson": {"policy": {"extraCharge": "3,000원"}},
        }
    ]
    parsed_results = {"room1": {"max_capacity": 6, "recommend_capacity": 4}}

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["extra_charge"] == 3000


@pytest.mark.asyncio
async def test_structured_extra_charge_has_priority_over_parser(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Room A",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": "RT01",
            "minBookingTime": 1,
            "extraFeeSettingJson": {"policy": {"extraCharge": "3,000원"}},
        }
    ]
    parsed_results = {"room1": {"max_capacity": 6, "recommend_capacity": 4, "extra_charge": 5000}}

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["extra_charge"] == 3000


@pytest.mark.asyncio
async def test_text_capacity_signals_override_parser_capacity(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "블랙룸 (정원 20명, 최대 30명)",
            "desc": "최소 2시간",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": "RT01",
            "minBookingTime": 2,
            "extraFeeSettingJson": {},
        }
    ]
    parsed_results = {"room1": {"max_capacity": 6}}

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["max_capacity"] == 30
    assert room_data["recommend_capacity"] == 30  # min(max_cap, FLAG) — CHECK 제약 준수


@pytest.mark.asyncio
async def test_text_recommend_range_used_for_capacity_range(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "화이트룸",
            "desc": "권장 4~6명, 최대 8명",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": "RT01",
            "minBookingTime": 1,
            "extraFeeSettingJson": {},
        }
    ]
    parsed_results = {"room1": {"max_capacity": 7, "recommend_capacity_range": None}}

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["max_capacity"] == 8
    assert room_data["recommend_capacity"] == 8  # min(max_cap, FLAG) — CHECK 제약 준수
    assert room_data["recommend_capacity_range"] == [4, 8]


@pytest.mark.asyncio
async def test_text_range_wins_when_both_text_and_parser_ranges_exist(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "화이트룸",
            "desc": "권장 4~6명, 최대 8명",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": "RT01",
            "minBookingTime": 1,
            "extraFeeSettingJson": {},
        }
    ]
    parsed_results = {
        "room1": {"max_capacity": 7, "recommend_capacity_range": [5, 7]}
    }

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["max_capacity"] == 8
    assert room_data["recommend_capacity"] == 8  # min(max_cap, FLAG) — CHECK 제약 준수
    assert room_data["recommend_capacity_range"] == [4, 8]


@pytest.mark.asyncio
async def test_structured_requires_call_overrides_parser(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Room A",
            "desc": "",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": "RT01",
            "minBookingTime": 1,
            "extraFeeSettingJson": {},
            "extraDescJson": {"requiresCallOnSameDay": True},
        }
    ]
    parsed_results = {
        "room1": {
            "max_capacity": 6,
            "recommend_capacity": 4,
            "requires_call_on_sameday": False,
        }
    }

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["requires_call_on_sameday"] is True


@pytest.mark.asyncio
async def test_parser_requires_call_used_when_structured_missing(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Room A",
            "desc": "",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": "RT01",
            "minBookingTime": 1,
            "extraFeeSettingJson": {},
        }
    ]
    parsed_results = {
        "room1": {
            "max_capacity": 6,
            "recommend_capacity": 4,
            "requires_call_on_sameday": True,
        }
    }

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["requires_call_on_sameday"] is True


@pytest.mark.asyncio
async def test_structured_text_requires_call_overrides_parser(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Room A",
            "desc": "",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": "RT01",
            "minBookingTime": 1,
            "extraFeeSettingJson": {},
            "extraDescJson": [
                {
                    "title": "예약 안내",
                    "context": "당일 예약은 전화 문의 필수입니다.",
                    "images": [],
                }
            ],
        }
    ]
    parsed_results = {
        "room1": {
            "max_capacity": 6,
            "recommend_capacity": 4,
            "requires_call_on_sameday": False,
        }
    }

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["requires_call_on_sameday"] is True


@pytest.mark.asyncio
async def test_structured_text_negative_requires_call_overrides_parser(service, mock_supabase):
    business = {
        "businessId": "biz1",
        "businessDisplayName": "Test",
        "coordinates": None,
    }
    rooms = [
        {
            "bizItemId": "room1",
            "name": "Room A",
            "desc": "",
            "bizItemResources": [],
            "minMaxPrice": {"minPrice": 10000},
            "bookingTimeUnitCode": "RT01",
            "minBookingTime": 1,
            "extraFeeSettingJson": {},
            "extraDescJson": [
                {
                    "title": "예약 안내",
                    "context": "당일 예약도 전화 문의 없이 가능합니다.",
                    "images": [],
                }
            ],
        }
    ]
    parsed_results = {
        "room1": {
            "max_capacity": 6,
            "recommend_capacity": 4,
            "requires_call_on_sameday": True,
        }
    }

    await service._save_to_db(business, rooms, parsed_results)

    upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
    room_data = upsert_call[0][0]
    assert room_data["requires_call_on_sameday"] is False

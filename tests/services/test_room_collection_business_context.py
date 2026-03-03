from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_collect_by_id_passes_business_desc_to_parser_batch():
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client"
    ):
        from app.services.room_collection_service import RoomCollectionService

        service = RoomCollectionService()

    service.room_fetcher.fetch_full_info = AsyncMock(
        return_value={
            "business": {
                "businessId": "522011",
                "businessDisplayName": "Test Studio",
                "desc": "Store-wide context for equipment and rules",
                "coordinates": {"latitude": 37.0, "longitude": 127.0},
            },
            "rooms": [
                {"bizItemId": "room-1", "name": "Room A", "desc": "Max 6", "minMaxPrice": {"minPrice": 10000}},
            ],
            "subway": None,
        }
    )
    service.parser_service.parse_room_desc_batch = AsyncMock(
        return_value={
            "room-1": {
                "clean_name": "Room A",
                "max_capacity": 6,
                "recommend_capacity": 4,
            }
        }
    )
    service._save_to_db = AsyncMock()
    service._export_unresolved = AsyncMock()

    await service.collect_by_id("522011")

    parse_items = service.parser_service.parse_room_desc_batch.await_args.args[0]
    assert len(parse_items) == 1
    assert parse_items[0]["id"] == "room-1"
    assert parse_items[0]["business_desc"] == "Store-wide context for equipment and rules"


@pytest.mark.asyncio
async def test_collect_by_id_keeps_inquiry_required_rooms_when_reservable():
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client"
    ):
        from app.services.room_collection_service import RoomCollectionService

        service = RoomCollectionService()

    service.room_fetcher.fetch_full_info = AsyncMock(
        return_value={
            "business": {
                "businessId": "522011",
                "businessDisplayName": "Test Studio",
                "desc": "Business context",
                "coordinates": {"latitude": 37.0, "longitude": 127.0},
            },
            "rooms": [
                {
                    "bizItemId": "room-call",
                    "name": "Room Call",
                    "desc": "당일 예약은 전화 문의 필수입니다.",
                    "minMaxPrice": {"minPrice": 15000},
                },
                {
                    "bizItemId": "room-ok",
                    "name": "Room OK",
                    "desc": "최대 6명",
                    "minMaxPrice": {"minPrice": 16000},
                },
            ],
            "subway": None,
        }
    )
    service.parser_service.parse_room_desc_batch = AsyncMock(
        return_value={"room-ok": {"clean_name": "Room OK", "max_capacity": 6, "recommend_capacity": 4}}
    )
    service._save_to_db = AsyncMock()
    service._export_unresolved = AsyncMock()

    await service.collect_by_id("522011")

    parse_items = service.parser_service.parse_room_desc_batch.await_args.args[0]
    assert len(parse_items) == 2
    assert {item["id"] for item in parse_items} == {"room-call", "room-ok"}
    saved_rooms = service._save_to_db.await_args.args[1]
    assert len(saved_rooms) == 2
    assert {room["bizItemId"] for room in saved_rooms} == {"room-call", "room-ok"}


@pytest.mark.asyncio
async def test_collect_by_id_filters_out_rooms_without_reservation_metadata():
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client"
    ):
        from app.services.room_collection_service import RoomCollectionService

        service = RoomCollectionService()

    service.room_fetcher.fetch_full_info = AsyncMock(
        return_value={
            "business": {
                "businessId": "706924",
                "businessDisplayName": "Test Studio",
                "desc": "Business context",
                "coordinates": {"latitude": 37.0, "longitude": 127.0},
            },
            "rooms": [
                {
                    "bizItemId": "room-no-meta",
                    "name": "Room No Meta",
                    "desc": "연습실 상세 설명",
                    "minMaxPrice": None,
                    "bookingCountSettingJson": None,
                    "bookingPrecautionJson": None,
                    "minBookingCount": None,
                    "maxBookingCount": None,
                    "minBookingTime": None,
                    "maxBookingTime": None,
                    "bookingTimeUnitCode": None,
                    "stock": None,
                },
                {
                    "bizItemId": "room-ok",
                    "name": "Room OK",
                    "desc": "최대 5명",
                    "minMaxPrice": {"minPrice": 12000},
                },
            ],
            "subway": None,
        }
    )
    service.parser_service.parse_room_desc_batch = AsyncMock(
        return_value={"room-ok": {"clean_name": "Room OK", "max_capacity": 5, "recommend_capacity": 3}}
    )
    service._save_to_db = AsyncMock()
    service._export_unresolved = AsyncMock()

    await service.collect_by_id("706924")

    parse_items = service.parser_service.parse_room_desc_batch.await_args.args[0]
    assert len(parse_items) == 1
    assert parse_items[0]["id"] == "room-ok"
    saved_rooms = service._save_to_db.await_args.args[1]
    assert len(saved_rooms) == 1
    assert saved_rooms[0]["bizItemId"] == "room-ok"


@pytest.mark.asyncio
async def test_collect_by_id_skips_when_all_rooms_filtered():
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client"
    ):
        from app.services.room_collection_service import RoomCollectionService

        service = RoomCollectionService()

    service.room_fetcher.fetch_full_info = AsyncMock(
        return_value={
            "business": {
                "businessId": "1384809",
                "businessDisplayName": "Filtered Studio",
                "desc": "",
                "coordinates": {"latitude": 37.0, "longitude": 127.0},
            },
            "rooms": [
                {
                    "bizItemId": "room-call",
                    "name": "Room Call",
                    "desc": "예약은 전화 문의 필수",
                    "minMaxPrice": None,
                    "bookingCountSettingJson": None,
                    "bookingPrecautionJson": None,
                    "minBookingCount": None,
                    "maxBookingCount": None,
                    "minBookingTime": None,
                    "maxBookingTime": None,
                    "bookingTimeUnitCode": None,
                    "stock": None,
                },
                {
                    "bizItemId": "room-no-meta",
                    "name": "Room No Meta",
                    "desc": "연습실",
                    "minMaxPrice": None,
                    "bookingCountSettingJson": None,
                    "bookingPrecautionJson": None,
                    "minBookingCount": None,
                    "maxBookingCount": None,
                    "minBookingTime": None,
                    "maxBookingTime": None,
                    "bookingTimeUnitCode": None,
                    "stock": None,
                },
            ],
            "subway": None,
        }
    )
    service.parser_service.parse_room_desc_batch = AsyncMock(return_value={})
    service._save_to_db = AsyncMock()
    service._export_unresolved = AsyncMock()

    await service.collect_by_id("1384809")

    service.parser_service.parse_room_desc_batch.assert_not_awaited()
    service._save_to_db.assert_not_awaited()
    service._export_unresolved.assert_not_awaited()

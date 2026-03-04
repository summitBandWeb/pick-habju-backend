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


@pytest.mark.asyncio
async def test_collect_by_id_skips_non_rehearsal_when_source_hint_has_no_domain_keyword():
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client"
    ):
        from app.services.room_collection_service import RoomCollectionService

        service = RoomCollectionService()

    service._source_item_hints["nondomain-1"] = {
        "id": "nondomain-1",
        "name": "Binary Creative Lab",
        "category": "엔터테인먼트",
    }
    service.room_fetcher.fetch_full_info = AsyncMock(
        return_value={
            "business": {
                "businessId": "nondomain-1",
                "businessDisplayName": "Binary Creative Lab",
                "desc": "콘텐츠 제작 스튜디오",
                "coordinates": {"latitude": 37.0, "longitude": 127.0},
            },
            "rooms": [
                {
                    "bizItemId": "room-1",
                    "name": "Studio A",
                    "desc": "촬영 전용",
                    "minMaxPrice": {"minPrice": 12000},
                }
            ],
            "subway": None,
        }
    )
    service.parser_service.parse_room_desc_batch = AsyncMock(return_value={})
    service._save_to_db = AsyncMock()
    service._export_unresolved = AsyncMock()

    result = await service.collect_by_id("nondomain-1")

    assert result["status"] == "skipped_non_rehearsal"
    service.parser_service.parse_room_desc_batch.assert_not_awaited()
    service._save_to_db.assert_not_awaited()
    service._export_unresolved.assert_not_awaited()


@pytest.mark.asyncio
async def test_collect_by_id_uses_source_hint_description_for_domain_decision():
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client"
    ):
        from app.services.room_collection_service import RoomCollectionService

        service = RoomCollectionService()

    # source_hint.description 에만 도메인 키워드가 있는 케이스를 검증한다.
    service._source_item_hints["desc-fallback-1"] = {
        "id": "desc-fallback-1",
        "name": "Binary Creative Lab",
        "description": "밴드합주 가능한 연습 공간",
    }
    service.room_fetcher.fetch_full_info = AsyncMock(
        return_value={
            "business": {
                "businessId": "desc-fallback-1",
                "businessDisplayName": "Binary Creative Lab",
                "desc": "",
                "coordinates": {"latitude": 37.0, "longitude": 127.0},
            },
            "rooms": [],
            "subway": None,
        }
    )
    service.parser_service.parse_room_desc_batch = AsyncMock(return_value={})
    service._save_to_db = AsyncMock()
    service._export_unresolved = AsyncMock()

    result = await service.collect_by_id("desc-fallback-1")

    assert result["status"] == "skipped_no_rooms"
    assert result["reason"] == "biz_items_empty"
    assert result["is_rehearsal_candidate"] is True
    assert "밴드합주" in result["positive_hits"]
    service.parser_service.parse_room_desc_batch.assert_not_awaited()
    service._save_to_db.assert_not_awaited()
    service._export_unresolved.assert_not_awaited()


@pytest.mark.asyncio
async def test_collect_by_id_returns_skip_reason_when_room_inventory_empty():
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client"
    ):
        from app.services.room_collection_service import RoomCollectionService

        service = RoomCollectionService()

    service._source_item_hints["habju-1"] = {
        "id": "habju-1",
        "name": "사당 합주실",
        "category": "연습실",
    }
    service.room_fetcher.fetch_full_info = AsyncMock(
        return_value={
            "business": {
                "businessId": "habju-1",
                "businessDisplayName": "사당 합주실",
                "desc": "합주 연습실",
                "coordinates": {"latitude": 37.0, "longitude": 127.0},
            },
            "rooms": [],
            "subway": None,
        }
    )
    service.parser_service.parse_room_desc_batch = AsyncMock(return_value={})
    service._save_to_db = AsyncMock()
    service._export_unresolved = AsyncMock()

    result = await service.collect_by_id("habju-1")

    assert result["status"] == "skipped_no_rooms"
    assert result["reason"] == "biz_items_empty"
    assert result["is_rehearsal_candidate"] is True
    service.parser_service.parse_room_desc_batch.assert_not_awaited()
    service._save_to_db.assert_not_awaited()


@pytest.mark.asyncio
async def test_collect_by_id_uses_place_page_representative_keywords_for_domain_decision():
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client"
    ):
        from app.services.room_collection_service import RoomCollectionService

        service = RoomCollectionService()

    service._source_item_hints["kw-fallback-1"] = {
        "id": "kw-fallback-1",
        "placeId": "244676732",
        "name": "헤일 뮤직 스튜디오",
    }
    service.map_crawler.reveal_representative_keywords = AsyncMock(return_value=["합주실", "음악연습실"])
    service.room_fetcher.fetch_full_info = AsyncMock(
        return_value={
            "business": {
                "businessId": "kw-fallback-1",
                "businessDisplayName": "헤일 뮤직 스튜디오",
                "desc": "실시간 예약 가능",
                "coordinates": {"latitude": 37.0, "longitude": 127.0},
            },
            "rooms": [
                {
                    "bizItemId": "room-1",
                    "name": "A room",
                    "desc": "최대 6명",
                    "minMaxPrice": {"minPrice": 15000},
                }
            ],
            "subway": None,
        }
    )
    service.parser_service.parse_room_desc_batch = AsyncMock(
        return_value={"room-1": {"clean_name": "A room", "max_capacity": 6, "recommend_capacity": 4}}
    )
    service._save_to_db = AsyncMock()
    service._export_unresolved = AsyncMock()

    result = await service.collect_by_id("kw-fallback-1")

    assert result["status"] == "collected"
    assert result["is_rehearsal_candidate"] is True
    assert "합주실" in result["representative_keywords"]
    service.map_crawler.reveal_representative_keywords.assert_awaited_once_with("244676732")
    service._save_to_db.assert_awaited()

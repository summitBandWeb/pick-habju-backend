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
                {"bizItemId": "room-1", "name": "Room A", "desc": "Max 6"},
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

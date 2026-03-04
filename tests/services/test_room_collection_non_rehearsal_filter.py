from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def service():
    with patch("app.services.room_collection_service.NaverMapCrawler"), patch(
        "app.services.room_collection_service.NaverRoomFetcher"
    ), patch("app.services.room_collection_service.RoomParserService"), patch(
        "app.services.room_collection_service.get_supabase_client"
    ):
        from app.services.room_collection_service import RoomCollectionService

        return RoomCollectionService()


def test_filter_rooms_excludes_lesson_and_recording_names(service):
    rooms = [
        {"bizItemId": "room-ok", "name": "A Room", "minMaxPrice": {"minPrice": 15000}},
        {"bizItemId": "room-lesson", "name": "재즈피아노 레슨", "minMaxPrice": {"minPrice": 20000}},
        {"bizItemId": "room-recording", "name": "레코딩 (녹음세션)", "minMaxPrice": {"minPrice": 25000}},
    ]

    selected, stats = service._filter_rooms_for_regex_parsing(rooms)

    assert len(selected) == 1
    assert selected[0]["bizItemId"] == "room-ok"
    assert stats["non_rehearsal_keyword"] == 2
    assert stats["missing_reservation"] == 0


@pytest.mark.asyncio
async def test_collect_by_id_skips_when_all_rooms_are_non_rehearsal_labels(service):
    service.room_fetcher.fetch_full_info = AsyncMock(
        return_value={
            "business": {
                "businessId": "1574159",
                "businessDisplayName": "Brown Studio",
                "desc": "test",
                "coordinates": {"latitude": 37.0, "longitude": 127.0},
            },
            "rooms": [
                {"bizItemId": "r1", "name": "재즈화성학레슨", "minMaxPrice": {"minPrice": 18000}},
                {"bizItemId": "r2", "name": "레코딩 (녹음세션)", "minMaxPrice": {"minPrice": 22000}},
            ],
            "subway": None,
        }
    )
    service.parser_service.parse_room_desc_batch = AsyncMock(return_value={})
    service._save_to_db = AsyncMock()
    service._export_unresolved = AsyncMock()

    result = await service.collect_by_id("1574159")

    assert result["status"] == "skipped_all_rooms_filtered"
    assert result["reason"] == "rooms_filtered_non_rehearsal_keywords"
    assert result["non_rehearsal_keyword"] == 2
    service.parser_service.parse_room_desc_batch.assert_not_awaited()
    service._save_to_db.assert_not_awaited()
    service._export_unresolved.assert_not_awaited()

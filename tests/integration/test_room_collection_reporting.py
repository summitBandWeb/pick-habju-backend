import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_collect_by_query_forces_priority_area_mode():
    with patch("app.services.room_collection_service.NaverMapCrawler") as mock_crawler_cls, \
         patch("app.services.room_collection_service.NaverRoomFetcher"), \
         patch("app.services.room_collection_service.RoomParserService"), \
         patch("app.services.room_collection_service.get_supabase_client"):
        from app.services.room_collection_service import RoomCollectionService

        mock_crawler = mock_crawler_cls.return_value
        mock_crawler.search_rehearsal_rooms = AsyncMock(
            return_value=[{"id": "biz1", "bookingBusinessId": "biz1", "name": "ok-room"}]
        )

        service = RoomCollectionService()
        service.map_crawler = mock_crawler
        service.collect_by_id = AsyncMock()

        result = await service.collect_by_query("hongdae practice room")

        assert result["mode"] == "priority_areas"
        assert result["requested_query"] == "hongdae practice room"
        assert result["total_unique"] == 1
        assert result["success"] == 1
        assert mock_crawler.search_rehearsal_rooms.call_count == 6


@pytest.mark.asyncio
async def test_collect_all_regions_uses_priority_area_mode():
    with patch("app.services.room_collection_service.NaverMapCrawler") as mock_crawler_cls, \
         patch("app.services.room_collection_service.NaverRoomFetcher"), \
         patch("app.services.room_collection_service.RoomParserService"), \
         patch("app.services.room_collection_service.get_supabase_client"):
        from app.services.room_collection_service import RoomCollectionService

        mock_crawler = mock_crawler_cls.return_value
        mock_crawler.search_rehearsal_rooms = AsyncMock(
            return_value=[{"id": "biz1", "bookingBusinessId": "biz1", "name": "ok-room"}]
        )

        service = RoomCollectionService()
        service.map_crawler = mock_crawler
        service.collect_by_id = AsyncMock()

        result = await service.collect_all_regions()

        assert result["mode"] == "priority_areas"
        assert result["total_unique"] == 1
        assert result["success"] == 1
        assert result["failed"] == 0
        assert mock_crawler.search_rehearsal_rooms.call_count == 6


@pytest.mark.asyncio
async def test_collect_priority_areas_deduplicates_overlapping_queries():
    with patch("app.services.room_collection_service.NaverMapCrawler") as mock_crawler_cls, \
         patch("app.services.room_collection_service.NaverRoomFetcher"), \
         patch("app.services.room_collection_service.RoomParserService"), \
         patch("app.services.room_collection_service.get_supabase_client"):
        from app.services.room_collection_service import RoomCollectionService

        mock_crawler = mock_crawler_cls.return_value
        mock_crawler.search_rehearsal_rooms = AsyncMock(
            side_effect=[
                [
                    {"id": "biz1", "bookingBusinessId": "biz1", "name": "A"},
                    {"id": "biz2", "bookingBusinessId": "biz2", "name": "B"},
                ],
                [
                    {"id": "biz2", "bookingBusinessId": "biz2", "name": "B"},
                    {"id": "biz3", "bookingBusinessId": "biz3", "name": "C"},
                ],
            ]
        )

        service = RoomCollectionService()
        service.map_crawler = mock_crawler
        service.collect_by_id = AsyncMock()

        result = await service.collect_priority_areas(["사당역 합주실", "합정역 합주실"])

        assert result["mode"] == "priority_areas"
        assert result["total_unique"] == 3
        assert result["success"] == 3
        assert result["failed"] == 0
        assert len(result["query_reports"]) == 2
        assert service.collect_by_id.call_count == 3


@pytest.mark.asyncio
async def test_collect_priority_areas_includes_source_queries_on_failure():
    with patch("app.services.room_collection_service.NaverMapCrawler") as mock_crawler_cls, \
         patch("app.services.room_collection_service.NaverRoomFetcher"), \
         patch("app.services.room_collection_service.RoomParserService"), \
         patch("app.services.room_collection_service.get_supabase_client"):
        from app.services.room_collection_service import RoomCollectionService

        mock_crawler = mock_crawler_cls.return_value
        mock_crawler.search_rehearsal_rooms = AsyncMock(
            return_value=[{"id": "biz1", "bookingBusinessId": "biz1", "name": "A"}]
        )

        service = RoomCollectionService()
        service.map_crawler = mock_crawler

        async def side_effect(business_id: str):
            raise RuntimeError(f"boom:{business_id}")

        service.collect_by_id = AsyncMock(side_effect=side_effect)

        result = await service.collect_priority_areas(["사당역 합주실"])

        assert result["success"] == 0
        assert result["failed"] == 1
        assert len(result["failures"]) == 1
        assert result["failures"][0]["business_id"] == "biz1"
        assert result["failures"][0]["source_queries"] == ["사당역 합주실"]


@pytest.mark.asyncio
async def test_collect_priority_areas_respects_max_targets():
    with patch("app.services.room_collection_service.NaverMapCrawler") as mock_crawler_cls, \
         patch("app.services.room_collection_service.NaverRoomFetcher"), \
         patch("app.services.room_collection_service.RoomParserService"), \
         patch("app.services.room_collection_service.get_supabase_client"):
        from app.services.room_collection_service import RoomCollectionService

        mock_crawler = mock_crawler_cls.return_value
        mock_crawler.search_rehearsal_rooms = AsyncMock(
            return_value=[
                {"id": "biz1", "bookingBusinessId": "biz1", "name": "A"},
                {"id": "biz2", "bookingBusinessId": "biz2", "name": "B"},
                {"id": "biz3", "bookingBusinessId": "biz3", "name": "C"},
            ]
        )

        service = RoomCollectionService()
        service.map_crawler = mock_crawler
        service.collect_by_id = AsyncMock()

        result = await service.collect_priority_areas(["사당역 합주실"], max_targets=2)

        assert result["total_unique_before_limit"] == 3
        assert result["total_unique"] == 2
        assert result["success"] == 2
        assert service.collect_by_id.call_count == 2

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_collect_by_query_includes_failure_details():
    with patch("app.services.room_collection_service.NaverMapCrawler") as mock_crawler_cls, \
         patch("app.services.room_collection_service.NaverRoomFetcher"), \
         patch("app.services.room_collection_service.RoomParserService"), \
         patch("app.services.room_collection_service.get_supabase_client"):
        from app.services.room_collection_service import RoomCollectionService

        mock_crawler = mock_crawler_cls.return_value
        mock_crawler.search_rehearsal_rooms = AsyncMock(return_value=[{"name": "broken-item"}])

        service = RoomCollectionService()
        service.map_crawler = mock_crawler
        service.collect_by_id = AsyncMock()

        result = await service.collect_by_query("hongdae practice room")

        assert result["success"] == 0
        assert result["failed"] == 1
        assert len(result["failures"]) == 1
        assert "missing business id" in result["failures"][0]["reason"]


@pytest.mark.asyncio
async def test_collect_all_regions_includes_failure_details():
    with patch("app.services.room_collection_service.NaverMapCrawler") as mock_crawler_cls, \
         patch("app.services.room_collection_service.NaverRoomFetcher"), \
         patch("app.services.room_collection_service.RoomParserService"), \
         patch("app.services.room_collection_service.get_supabase_client"):
        from app.services.room_collection_service import RoomCollectionService

        mock_crawler = mock_crawler_cls.return_value
        mock_crawler.crawl_all_regions = AsyncMock(
            return_value=[{"id": "biz1", "name": "ok-room"}, {"name": "broken-room"}]
        )

        service = RoomCollectionService()
        service.map_crawler = mock_crawler
        service.collect_by_id = AsyncMock()

        result = await service.collect_all_regions()

        assert result["total"] == 2
        assert result["success"] == 1
        assert result["failed"] == 1
        assert len(result["failures"]) == 1
        assert "missing business id" in result["failures"][0]["reason"]

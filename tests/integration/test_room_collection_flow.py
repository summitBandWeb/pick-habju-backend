# tests/integration/test_room_collection_flow.py
"""
RoomCollectionService 통합 테스트

테스트 대상:
- collect_by_id: Fetch → Parse → Save 전체 흐름

실행: pytest tests/integration/test_room_collection_flow.py -v
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestCollectByIdFlow:
    """collect_by_id 전체 흐름 통합 테스트"""
    
    @pytest.fixture
    def mock_fetcher(self):
        """NaverRoomFetcher Mock"""
        mock = MagicMock()
        mock.fetch_full_info = AsyncMock(return_value={
            "business": {
                "businessId": "test123",
                "businessDisplayName": "테스트 합주실"
            },
            "rooms": [
                {
                    "bizItemId": "room1",
                    "name": "[평일] A룸",
                    "desc": "최대 6인, 기본 4인, 1인 추가시 3000원",
                    "bizItemResources": [
                        {"resourceUrl": "https://example.com/img1.jpg"},
                        {"resourceUrl": "https://example.com/img2.jpg"}
                    ],
                    "minMaxPrice": {"minPrice": 15000, "maxPrice": 25000}
                },
                {
                    "bizItemId": "room2",
                    "name": "B룸 (주말)",
                    "desc": "4~6인 권장",
                    "bizItemResources": [],
                    "minMaxPrice": {"minPrice": 20000}
                }
            ]
        })
        return mock
    
    @pytest.fixture
    def mock_parser(self):
        """RoomParserService Mock"""
        mock = MagicMock()
        mock.parse_room_desc_batch = AsyncMock(return_value={
            "room1": {
                "clean_name": "A룸",
                "day_type": "weekday",
                "max_capacity": 6,
                "recommend_capacity": 4,
                "base_capacity": 4,
                "extra_charge": 3000,
                "requires_call_on_same_day": False
            },
            "room2": {
                "clean_name": "B룸",
                "day_type": "weekend",
                "max_capacity": 6,
                "recommend_capacity": 5,
                "base_capacity": None,
                "extra_charge": None,
                "requires_call_on_same_day": False
            }
        })
        return mock
    
    @pytest.fixture
    def mock_supabase(self):
        """Supabase Mock"""
        mock = MagicMock()
        mock.table.return_value.upsert.return_value.execute.return_value = MagicMock()
        mock.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return mock
    
    @pytest.fixture
    def service(self, mock_fetcher, mock_parser, mock_supabase):
        """통합 테스트용 서비스 인스턴스"""
        with patch('app.services.room_collection_service.NaverMapCrawler'), \
             patch('app.services.room_collection_service.NaverRoomFetcher', return_value=mock_fetcher), \
             patch('app.services.room_collection_service.RoomParserService', return_value=mock_parser), \
             patch('app.services.room_collection_service.get_supabase_client', return_value=mock_supabase):
            from app.services.room_collection_service import RoomCollectionService
            svc = RoomCollectionService()
            svc.room_fetcher = mock_fetcher
            svc.parser_service = mock_parser
            svc.supabase = mock_supabase
            return svc
    
    # ============== IT01: 정상 수집 흐름 ==============
    @pytest.mark.asyncio
    async def test_collect_by_id_success(self, service, mock_fetcher, mock_parser, mock_supabase):
        """collect_by_id 정상 흐름 검증"""
        await service.collect_by_id("test123")
        
        # 1. Fetcher가 호출되었는지
        mock_fetcher.fetch_full_info.assert_called_once_with("test123")
        
        # 2. Parser가 호출되었는지
        mock_parser.parse_room_desc_batch.assert_called_once()
        parse_args = mock_parser.parse_room_desc_batch.call_args[0][0]
        assert len(parse_args) == 2
        assert parse_args[0]["id"] == "room1"
        
        # 3. Supabase에 Branch와 Room이 저장되었는지
        upsert_calls = mock_supabase.table.return_value.upsert.call_args_list
        assert len(upsert_calls) >= 3  # 1 branch + 2 rooms
    
    # ============== IT02: Room 데이터 검증 ==============
    @pytest.mark.asyncio
    async def test_room_data_structure(self, service, mock_supabase):
        """저장되는 Room 데이터 구조 검증"""
        await service.collect_by_id("test123")
        
        # Room upsert 호출 확인 (마지막 2개가 room)
        upsert_calls = mock_supabase.table.return_value.upsert.call_args_list
        
        # room1 데이터 검증
        room1_data = None
        for call in upsert_calls:
            data = call[0][0]
            if isinstance(data, dict) and data.get("biz_item_id") == "room1":
                room1_data = data
                break
        
        assert room1_data is not None
        assert room1_data["business_id"] == "test123"
        assert room1_data["name"] == "[평일] A룸"
        assert room1_data["price_per_hour"] == 15000
        assert room1_data["max_capacity"] == 6
        assert room1_data["recommend_capacity"] == 4
        assert room1_data["base_capacity"] == 4
        assert room1_data["extra_charge"] == 3000
        assert len(room1_data["image_urls"]) == 2
    
    # ============== IT03: Fetcher 실패 시 예외 ==============
    @pytest.mark.asyncio
    async def test_collect_by_id_fetch_failure(self, service, mock_fetcher):
        """Fetcher가 None 반환 시 ValueError 발생"""
        mock_fetcher.fetch_full_info.return_value = None
        
        with pytest.raises(ValueError, match="No data found"):
            await service.collect_by_id("invalid_id")
    
    # ============== IT04: Room이 없는 경우 ==============
    @pytest.mark.asyncio
    async def test_collect_by_id_no_rooms(self, service, mock_fetcher, mock_parser):
        """Room이 없는 Business는 Parser 호출 없이 종료"""
        mock_fetcher.fetch_full_info.return_value = {
            "business": {"businessId": "test123", "businessDisplayName": "빈 합주실"},
            "rooms": []
        }
        
        await service.collect_by_id("test123")
        
        # Parser는 호출되지 않아야 함
        mock_parser.parse_room_desc_batch.assert_not_called()


class TestCollectByQueryFlow:
    """collect_by_query 통합 테스트"""
    
    @pytest.fixture
    def mock_crawler(self):
        """NaverMapCrawler Mock"""
        mock = MagicMock()
        mock.search_rehearsal_rooms = AsyncMock(return_value=[
            {"id": "biz1", "name": "합주실A"},
            {"id": "biz2", "name": "합주실B"}
        ])
        return mock
    
    @pytest.fixture
    def service(self, mock_crawler):
        """통합 테스트용 서비스 인스턴스"""
        with patch('app.services.room_collection_service.NaverMapCrawler', return_value=mock_crawler), \
             patch('app.services.room_collection_service.NaverRoomFetcher'), \
             patch('app.services.room_collection_service.RoomParserService'), \
             patch('app.services.room_collection_service.get_supabase_client'):
            from app.services.room_collection_service import RoomCollectionService
            svc = RoomCollectionService()
            svc.map_crawler = mock_crawler
            # collect_by_id를 Mock으로 대체
            svc.collect_by_id = AsyncMock()
            return svc
    
    # ============== IT05: Query 검색 후 각 ID 수집 ==============
    @pytest.mark.asyncio
    async def test_collect_by_query_calls_collect_by_id(self, service, mock_crawler):
        """검색 결과 각 ID에 대해 collect_by_id 호출"""
        result = await service.collect_by_query("홍대 합주실")
        
        # Crawler가 검색 호출됨
        mock_crawler.search_rehearsal_rooms.assert_called_once_with("홍대 합주실")
        
        # 각 결과에 대해 collect_by_id 호출됨
        assert service.collect_by_id.call_count == 2
        service.collect_by_id.assert_any_call("biz1")
        service.collect_by_id.assert_any_call("biz2")
        
        # 성공 카운트 확인
        assert result["success"] == 2
        assert result["failed"] == 0
    
    # ============== IT06: 일부 실패 시 카운트 ==============
    @pytest.mark.asyncio
    async def test_collect_by_query_partial_failure(self, service, mock_crawler):
        """일부 수집 실패 시 카운트 검증"""
        # biz2 수집 시 예외 발생
        async def side_effect(bid):
            if bid == "biz2":
                raise Exception("수집 실패")
        
        service.collect_by_id.side_effect = side_effect
        
        result = await service.collect_by_query("홍대 합주실")
        
        assert result["success"] == 1
        assert result["failed"] == 1

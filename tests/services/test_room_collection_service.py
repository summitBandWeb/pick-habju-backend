# tests/services/test_room_collection_service.py
"""
RoomCollectionService 단위 테스트

테스트 대상:
- _extract_price: 가격 정보 추출
- Data Preservation Logic: 기존 값 보존 로직

실행: pytest tests/services/test_room_collection_service.py -v
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestExtractPrice:
    """_extract_price 메서드 테스트"""
    
    @pytest.fixture
    def service(self):
        """의존성을 Mock으로 대체한 서비스 인스턴스"""
        with patch('app.services.room_collection_service.NaverMapCrawler'), \
             patch('app.services.room_collection_service.NaverRoomFetcher'), \
             patch('app.services.room_collection_service.RoomParserService'), \
             patch('app.services.room_collection_service.get_supabase_client'):
            from app.services.room_collection_service import RoomCollectionService
            return RoomCollectionService()
    
    # ============== TC09: 정상 가격 추출 ==============
    def test_extract_price_normal(self, service):
        """minMaxPrice에서 minPrice 추출"""
        room = {"minMaxPrice": {"minPrice": 15000, "maxPrice": 25000}}
        result = service._extract_price(room)
        
        assert result == 15000
    
    # ============== TC10: minMaxPrice가 None ==============
    def test_extract_price_none(self, service):
        """minMaxPrice가 None인 경우"""
        room = {"minMaxPrice": None}
        result = service._extract_price(room)
        
        assert result is None
    
    # ============== TC11: minMaxPrice 키 없음 ==============
    def test_extract_price_missing_key(self, service):
        """minMaxPrice 키가 없는 경우"""
        room = {}
        result = service._extract_price(room)
        
        assert result is None
    
    # ============== TC: minPrice만 있는 경우 ==============
    def test_extract_price_only_min(self, service):
        """minPrice만 있는 경우"""
        room = {"minMaxPrice": {"minPrice": 10000}}
        result = service._extract_price(room)
        
        assert result == 10000


class TestDataPreservationLogic:
    """Data Preservation 로직 테스트 (DB Mock 사용)"""
    
    @pytest.fixture
    def mock_supabase(self):
        """Supabase 클라이언트 Mock"""
        mock = MagicMock()
        mock.table.return_value.upsert.return_value.execute.return_value = MagicMock()
        mock.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return mock
    
    @pytest.fixture
    def service(self, mock_supabase):
        """의존성을 Mock으로 대체한 서비스 인스턴스"""
        with patch('app.services.room_collection_service.NaverMapCrawler'), \
             patch('app.services.room_collection_service.NaverRoomFetcher'), \
             patch('app.services.room_collection_service.RoomParserService'), \
             patch('app.services.room_collection_service.get_supabase_client', return_value=mock_supabase):
            from app.services.room_collection_service import RoomCollectionService
            svc = RoomCollectionService()
            svc.supabase = mock_supabase
            return svc
    
    # ============== TC12: 새 값=1, 기존 값=10 → 기존 값 유지 ==============
    @pytest.mark.asyncio
    async def test_preserve_existing_valid_value(self, service, mock_supabase):
        """파싱 값이 기본값(1)이고 기존 값이 유효(10)하면 기존 값 유지"""
        # Setup: 기존 DB에 max_capacity=10인 데이터 존재
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"biz_item_id": "room1", "max_capacity": 10, "recommend_capacity": 8, "price_per_hour": 20000}]
        )
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"room1": {"max_capacity": 1, "recommend_capacity": 1}}  # LLM이 기본값 반환
        
        await service._save_to_db(business, rooms, parsed_results)
        
        # Verify: upsert 호출 시 max_capacity=10 (기존 값 유지)
        upsert_call = mock_supabase.table.return_value.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        assert upsert_data["max_capacity"] == 10
        assert upsert_data["recommend_capacity"] == 8
    
    # ============== TC13: 새 값=5, 기존 값=10 → 새 값으로 업데이트 ==============
    @pytest.mark.asyncio
    async def test_update_with_new_valid_value(self, service, mock_supabase):
        """파싱 값이 유효(5)하면 새 값으로 업데이트"""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"biz_item_id": "room1", "max_capacity": 10, "recommend_capacity": 8, "price_per_hour": 20000}]
        )
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"room1": {"max_capacity": 5, "recommend_capacity": 4}}  # LLM이 유효한 값 반환
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase.table.return_value.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        assert upsert_data["max_capacity"] == 5
        assert upsert_data["recommend_capacity"] == 4
    
    # ============== TC14: 새 값=8, 기존 값=1 → 새 값으로 업데이트 ==============
    @pytest.mark.asyncio
    async def test_update_when_existing_is_default(self, service, mock_supabase):
        """기존 값이 기본값(1)이면 새 값으로 업데이트"""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"biz_item_id": "room1", "max_capacity": 1, "recommend_capacity": 1, "price_per_hour": None}]
        )
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"room1": {"max_capacity": 8, "recommend_capacity": 6}}
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase.table.return_value.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        assert upsert_data["max_capacity"] == 8
        assert upsert_data["recommend_capacity"] == 6
    
    # ============== TC15: 기존 값 없음, 새 값=1 → 새 값 사용 ==============
    @pytest.mark.asyncio
    async def test_use_new_value_when_no_existing(self, service, mock_supabase):
        """기존 데이터가 없으면 새 값 그대로 사용"""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"room1": {"max_capacity": 1, "recommend_capacity": 1}}
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase.table.return_value.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        assert upsert_data["max_capacity"] == 1
        assert upsert_data["recommend_capacity"] == 1
    
    # ============== TC: 가격 보존 로직 ==============
    @pytest.mark.asyncio
    async def test_preserve_existing_price(self, service, mock_supabase):
        """새 가격이 0/None이고 기존 가격이 유효하면 기존 값 유지"""
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"biz_item_id": "room1", "max_capacity": 5, "recommend_capacity": 4, "price_per_hour": 25000}]
        )
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": None}]  # 가격 없음
        parsed_results = {"room1": {"max_capacity": 5, "recommend_capacity": 4}}
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase.table.return_value.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        assert upsert_data["price_per_hour"] == 25000  # 기존 가격 유지

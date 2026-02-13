# tests/services/test_room_collection_service.py
"""
RoomCollectionService 단위 테스트

테스트 대상:
- _extract_price: 가격 정보 추출
- Data Preservation Logic: 기존 값 보존 로직
- [v2.0.0] recommend_capacity_range / price_config 저장 검증

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
        """Supabase 클라이언트 Mock (테이블별 분리)

        Rationale:
            단일 mock.table.return_value로 모든 테이블 호출을 받으면
            upsert 호출 순서에 의존하는 취약한 assertion이 됨.
            table('room')과 table('branch')를 별도 Mock으로 분리.
        """
        mock = MagicMock()

        mock_room_table = MagicMock()
        mock_room_table.upsert.return_value.execute.return_value = MagicMock()
        mock_room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        mock_branch_table = MagicMock()
        mock_branch_table.upsert.return_value.execute.return_value = MagicMock()

        def table_dispatcher(name):
            if name == "room":
                return mock_room_table
            elif name == "branch":
                return mock_branch_table
            return MagicMock()

        mock.table.side_effect = table_dispatcher
        mock._room_table = mock_room_table
        mock._branch_table = mock_branch_table
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


class TestV2NewFields:
    """[v2.0.0] 신규 필드(recommend_capacity_range, price_config, display_name) 저장 검증"""
    
    @pytest.fixture
    def mock_supabase(self):
        """Supabase 클라이언트 Mock (테이블별 분리)

        Rationale:
            단일 mock.table.return_value로 모든 테이블 호출을 받으면
            upsert 호출 순서에 의존하는 취약한 assertion이 됨.
            table('room')과 table('branch')를 별도 Mock으로 분리.
        """
        mock = MagicMock()

        mock_room_table = MagicMock()
        mock_room_table.upsert.return_value.execute.return_value = MagicMock()
        mock_room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        mock_branch_table = MagicMock()
        mock_branch_table.upsert.return_value.execute.return_value = MagicMock()

        def table_dispatcher(name):
            if name == "room":
                return mock_room_table
            elif name == "branch":
                return mock_branch_table
            return MagicMock()

        mock.table.side_effect = table_dispatcher
        mock._room_table = mock_room_table
        mock._branch_table = mock_branch_table
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
    
    # ============== TC: recommend_capacity_range 저장 ==============
    @pytest.mark.asyncio
    async def test_saves_recommend_capacity_range_from_parser(self, service, mock_supabase):
        """파싱된 범위가 유효하면 우선 사용: [4, 6] → 검증 통과 → [4, 6] (max_cap=8 이내)
        
        Rationale:
            v2 리팩토링으로 유효한 parsed_range를 규칙 기반 계산보다 우선 사용하도록 변경.
            [4, 6]은 2개 정수, min<=max, 1~50 범위이므로 검증 통과.
            max_cap(8) 이내이므로 clamp 없이 그대로 반환.
        """
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실", "coordinates": None}
        rooms = [{"bizItemId": "r1", "name": "룸A", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {
            "r1": {
                "max_capacity": 8,
                "recommend_capacity": 5,
                "recommend_capacity_range": [4, 6],
                "price_config": [],
                "base_capacity": None,
                "extra_charge": None,
                "requires_call_on_same_day": False
            }
        }
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase.table.return_value.upsert.call_args_list[-1]
        room_data = upsert_call[0][0]
        
        # NOTE: 유효한 parsed_range [4, 6]이 우선 사용됨
        assert room_data["recommend_capacity_range"] == [4, 6]
        assert room_data["price_config"] == []
    
    # ============== TC: range 없으면 [n, n] Fallback ==============
    @pytest.mark.asyncio
    async def test_fallback_range_from_single_capacity(self, service, mock_supabase):
        """파서가 범위를 반환하지 않으면 규칙 기반으로 계산
        
        Rationale:
            extra_charge=None → [rec_cap, min(rec_cap+2, max_cap)] = [4, 6]
        """
        business = {"businessId": "biz1", "businessDisplayName": "테스트", "coordinates": None}
        rooms = [{"bizItemId": "r1", "name": "룸A", "bizItemResources": [], "minMaxPrice": {"minPrice": 10000}}]
        parsed_results = {
            "r1": {
                "max_capacity": 6,
                "recommend_capacity": 4,
                "recommend_capacity_range": None,
                "base_capacity": None,
                "extra_charge": None,
                "requires_call_on_same_day": False
            }
        }
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase.table.return_value.upsert.call_args_list[-1]
        room_data = upsert_call[0][0]
        
        # NOTE: 규칙 기반 → [4, min(6, 6)] = [4, 6]
        assert room_data["recommend_capacity_range"] == [4, 6]
    
    # ============== TC: display_name 저장 ==============
    @pytest.mark.asyncio
    async def test_saves_display_name_to_branch(self, service, mock_supabase):
        """Branch upsert 시 display_name이 포함되는지 검증"""
        business = {
            "businessId": "biz1",
            "businessDisplayName": "테스트 합주실 1호점",
            "coordinates": {"latitude": 37.5, "longitude": 127.0}
        }
        rooms = []
        parsed_results = {}
        
        await service._save_to_db(business, rooms, parsed_results)
        
        # Branch upsert 호출 확인
        upsert_call = mock_supabase.table.return_value.upsert.call_args_list[0]
        branch_data = upsert_call[0][0]
        
        assert branch_data["display_name"] == "테스트 합주실 1호점"
        assert branch_data["lat"] == 37.5
        assert branch_data["lng"] == 127.0
    
    # ============== TC: price_config 저장 ==============
    @pytest.mark.asyncio
    async def test_saves_price_config(self, service, mock_supabase):
        """복잡한 price_config가 DB에 정상 저장되는지 검증"""
        price_cfg = [
            {"day_type": "weekday", "price_per_hour": 15000},
            {"day_type": "weekend", "price_per_hour": 20000}
        ]
        business = {"businessId": "biz1", "businessDisplayName": "테스트", "coordinates": None}
        rooms = [{"bizItemId": "r1", "name": "룸A", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {
            "r1": {
                "max_capacity": 6,
                "recommend_capacity": 4,
                "recommend_capacity_range": [4, 4],
                "price_config": price_cfg,
                "base_capacity": None,
                "extra_charge": None,
                "requires_call_on_same_day": False
            }
        }
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase.table.return_value.upsert.call_args_list[-1]
        room_data = upsert_call[0][0]
        
        assert room_data["price_config"] == price_cfg

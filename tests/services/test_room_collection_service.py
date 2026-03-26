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
        mock_supabase._room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"biz_item_id": "room1", "max_capacity": 10, "recommend_capacity": 8, "price_per_hour": 20000}]
        )
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"room1": {"max_capacity": 1, "recommend_capacity": 1}}  # LLM이 기본값 반환
        
        await service._save_to_db(business, rooms, parsed_results)
        
        # Verify: upsert 호출 시 max_capacity=10 (기존 값 유지)
        upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        assert upsert_data["max_capacity"] == 10
        assert upsert_data["recommend_capacity"] == 100  # hardcoded MANUAL_REVIEW_FLAG
    
    # ============== TC13: 새 값=5, 기존 값=10 → 새 값으로 업데이트 ==============
    @pytest.mark.asyncio
    async def test_update_with_new_valid_value(self, service, mock_supabase):
        """파싱 값이 유효(5)하면 새 값으로 업데이트"""
        mock_supabase._room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"biz_item_id": "room1", "max_capacity": 10, "recommend_capacity": 8, "price_per_hour": 20000}]
        )
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"room1": {"max_capacity": 5, "recommend_capacity": 4}}  # LLM이 유효한 값 반환
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        assert upsert_data["max_capacity"] == 5
        assert upsert_data["recommend_capacity"] == 100  # hardcoded MANUAL_REVIEW_FLAG
    
    # ============== TC14: 새 값=8, 기존 값=1 → 새 값으로 업데이트 ==============
    @pytest.mark.asyncio
    async def test_update_when_existing_is_default(self, service, mock_supabase):
        """기존 값이 기본값(1)이면 새 값으로 업데이트"""
        mock_supabase._room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"biz_item_id": "room1", "max_capacity": 1, "recommend_capacity": 1, "price_per_hour": None}]
        )
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"room1": {"max_capacity": 8, "recommend_capacity": 6}}
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        assert upsert_data["max_capacity"] == 8
        assert upsert_data["recommend_capacity"] == 100  # hardcoded MANUAL_REVIEW_FLAG
    
    # ============== TC15: 기존 값 없음, 새 값=1 → 새 값 사용 ==============
    @pytest.mark.asyncio
    async def test_use_new_value_when_no_existing(self, service, mock_supabase):
        """기존 데이터가 없으면 새 값 그대로 사용"""
        mock_supabase._room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"room1": {"max_capacity": 1, "recommend_capacity": 1}}
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        assert upsert_data["max_capacity"] == 1
        assert upsert_data["recommend_capacity"] == 100  # hardcoded MANUAL_REVIEW_FLAG
    
    # ============== TC: 가격 보존 로직 ==============
    @pytest.mark.asyncio
    async def test_preserve_existing_price(self, service, mock_supabase):
        """새 가격이 0/None이고 기존 가격이 유효하면 기존 값 유지"""
        mock_supabase._room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"biz_item_id": "room1", "max_capacity": 5, "recommend_capacity": 4, "price_per_hour": 25000}]
        )
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": None}]  # 가격 없음
        parsed_results = {"room1": {"max_capacity": 5, "recommend_capacity": 4}}
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        assert upsert_data["price_per_hour"] == 25000  # 기존 가격 유지

    # ============== TC: 불리언 필드 보존 로직 ==============
    @pytest.mark.asyncio
    async def test_preserve_boolean_fields(self, service, mock_supabase):
        """파서에서 추출하지 못한 불리언(None)은 대상 기존(DB)의 불리언 값 유지"""
        mock_supabase._room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"biz_item_id": "room1", "can_reserve_one_hour": False, "requires_call_on_sameday": True}]
        )
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        # 파싱 결과에 None으로 명시되거나 아예 키가 없는 경우
        parsed_results = {
            "room1": {
                "max_capacity": 5, 
                "recommend_capacity": 4, 
                "can_reserve_one_hour": None, 
                "requires_call_on_sameday": None
            }
        }
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        # 기존 데이터를 유지해야 함
        assert upsert_data["can_reserve_one_hour"] is False
        assert upsert_data["requires_call_on_sameday"] is True

    @pytest.mark.asyncio
    async def test_override_boolean_fields(self, service, mock_supabase):
        """파서에서 추출한 명시적 불리언(False/True)은 기존 DB를 덮어씀"""
        mock_supabase._room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"biz_item_id": "room1", "can_reserve_one_hour": True, "requires_call_on_sameday": False}]
        )
        
        business = {"businessId": "biz1", "businessDisplayName": "테스트 합주실"}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        
        parsed_results = {
            "room1": {
                "max_capacity": 5, 
                "recommend_capacity": 4, 
                "can_reserve_one_hour": False, # 새로 파싱됨
                "requires_call_on_sameday": True # 새로 파싱됨
            }
        }
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        
        # 새로운 값으로 덮어써야 함
        assert upsert_data["can_reserve_one_hour"] is False
        assert upsert_data["requires_call_on_sameday"] is True

    @pytest.mark.asyncio
    async def test_legacy_boolean_parsing(self, service, mock_supabase):
        """파서가 requires_call_on_sameday를 출력하면 upsert에 정상 반영되는지 검증"""
        mock_supabase._room_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"biz_item_id": "room1", "can_reserve_one_hour": True, "requires_call_on_sameday": False}]
        )
        business = {"businessId": "biz1", "businessDisplayName": "테스트", "coordinates": None}
        rooms = [{"bizItemId": "room1", "name": "룸1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {
            "room1": {
                "max_capacity": 5,
                "recommend_capacity": 4,
                "requires_call_on_sameday": True
            }
        }
        await service._save_to_db(business, rooms, parsed_results)
        upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
        upsert_data = upsert_call[0][0]
        assert upsert_data["can_reserve_one_hour"] is True
        assert upsert_data["requires_call_on_sameday"] is True


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
                "requires_call_on_sameday": False
            }
        }
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
        room_data = upsert_call[0][0]
        
        # NOTE: 유효한 parsed_range [4, 6]이 우선 사용됨
        assert room_data["recommend_capacity_range"] == [4, 6]
        assert room_data["price_config"] == []
    
    # ============== TC: rec_cap/max_cap 모두 FLAG → None 반환 (#264) ==============
    def test_capacity_range_is_none_when_both_flag(self, service):
        """rec_cap, max_cap 모두 FLAG(100)이면 None 반환

        AS-IS: sentinel clamp(100→50) 후 delta 적용 → [49, 50] 같은 허구 범위 생성
        TO-BE: 근거 없음 → None 반환 (#264)

        Rationale:
            _save_to_db 경유 시 가격 밴드(5k~)가 항상 FLAG를 교체하므로 이 경로를
            통합 테스트로 검증할 수 없다. 파이프라인 전제(유효 가격 필수)가 바뀌면
            이 단위 테스트가 최후 방어선이 됨.
        """
        result = service._calculate_capacity_range(
            parsed_range=None,
            max_cap=100,
            base_cap=None,
            extra_charge=None,
        )
        assert result is None

    # ============== TC: rec_cap 유효, max_cap FLAG → range 정상 계산 (#264) ==============
    def test_capacity_range_computed_without_flag_max_cap(self, service):
        """max_cap이 FLAG(100)인 경우 effective_max_cap=0 → None

        AS-IS: FLAG max_cap을 50으로 clamp 후 delta 적용
        TO-BE: rec_cap 파라미터 제거됨. max_cap=FLAG → effective=0 → None
        """
        result = service._calculate_capacity_range(
            parsed_range=None,
            max_cap=100,
            base_cap=None,
            extra_charge=None,
        )
        # max_cap=FLAG → effective_max_cap=0 → step 3 → None
        assert result is None

    # ============== TC: rec_cap FLAG, max_cap 유효 → Precondition 위반 방어 (#264) ==============
    def test_capacity_range_none_when_rec_cap_flag_only(self, service):
        """rec_cap=FLAG, max_cap=유효 — Precondition 위반 케이스 방어적 None 반환

        save_to_db 정상 흐름에서는 발생하지 않으나,
        파서가 recommend_capacity=100을 직접 반환하는 경우 위반 가능.
        rec_cap 기반 step 4 계산([99, 99])보다 None이 안전하다.
        """
        result = service._calculate_capacity_range(
            parsed_range=None,
            max_cap=5,
            base_cap=None,
            extra_charge=None,
        )
        # rec_cap 파라미터 제거됨. max_cap=5 → step 4: 5//2=2, ±1 → [1, 3]
        assert result == [1, 3]

    # ============== TC: rec_cap=0, max_cap=0 → [1,1] 허구 범위 생성 방지 ==============
    def test_capacity_range_none_when_both_zero(self, service):
        """rec_cap=0, max_cap=0, parsed_range=None → None 반환 (허구 [1,1] 방지)

        파서가 max_capacity=0을 반환하면 _save_to_db에서 FLAG로 올리지 않고 통과.
        step 4에서 min_c=max(-1,1)=1, max_c=1 → [1,1] 이 생성되는 경로를 차단.
        """
        result = service._calculate_capacity_range(
            parsed_range=None,
            max_cap=0,
            base_cap=None,
            extra_charge=None,
        )
        assert result is None

    # ============== TC: extra_charge + max_cap FLAG → [base_cap, base_cap] (P1-2) ==============
    def test_capacity_range_single_value_when_extra_charge_and_flag_max_cap(self, service):
        """extra_charge 유효 + base_cap 유효 + max_cap FLAG → [base_cap, base_cap]

        max_cap이 FLAG면 effective_max_cap=0 → real_max = base_cap → [base_cap, base_cap].
        상한을 알 수 없으나 기준 인원은 신뢰할 수 있는 경우의 의도된 동작.
        """
        result = service._calculate_capacity_range(
            parsed_range=None,
            max_cap=100,    # FLAG
            base_cap=6,
            extra_charge=5000,
        )
        # effective_max_cap=0 → real_max = max(0, 6) if 0>0 else 6 = 6 → [6, 6]
        assert result == [6, 6]

    # ============== TC: extra_charge 있으나 base_cap FLAG → rec_cap ±1 fallback (#264) ==============
    def test_capacity_range_fallback_when_extra_charge_but_flag_base_cap(self, service):
        """extra_charge가 있어도 base_cap이 FLAG(100)이면 effective_base_cap=None
        → step 3 스킵 → rec_cap ±1 fallback

        Rationale:
            추가 요금 기준 인원을 신뢰할 수 없으면 [base_cap, max_cap] 형태 계산 불가.
            rec_cap 기반 ±1이 차선책. 허구 base_cap으로 범위를 만들지 않는다.
        """
        result = service._calculate_capacity_range(
            parsed_range=None,
            max_cap=8,
            base_cap=100,       # FLAG
            extra_charge=5000,
        )
        # base_cap=FLAG → effective_base_cap=None → step 2 스킵 → step 4: 8//2=4, ±1 → [3, 5]
        assert result == [3, 5]

    # ============== TC: range 없으면 ±1 Fallback ==============
    @pytest.mark.asyncio
    async def test_fallback_range_from_single_capacity(self, service, mock_supabase):
        """파서가 범위를 반환하지 않으면 규칙 기반으로 계산

        Rationale:
            모든 rec_cap에 대해 ±1 고정 (delta=1, #258)
            rec=4, price=10000 → price band(10k_15k) 적용 → rec=4, ±1 → [3, 5]
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
                "requires_call_on_sameday": False
            }
        }

        await service._save_to_db(business, rooms, parsed_results)

        upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
        room_data = upsert_call[0][0]

        # rec_cap 제거됨 → step 4: max=6, 6//2=3, ±1 → [2, 4]
        assert room_data["recommend_capacity_range"] == [2, 4]
    
    # ============== TC: display_name 저장 ==============
    @pytest.mark.asyncio
    async def test_saves_display_name_to_branch(self, service, mock_supabase):
        """Branch upsert 시 display_name이 포함되는지 검증"""
        business = {
            "businessId": "biz1",
            "businessDisplayName": "테스트 합주실 1호점",
            "coordinates": {"latitude": 37.5, "longitude": 127.0}
        }
        rooms = [{"bizItemId": "r1", "name": "룸A", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"r1": {}}
        
        await service._save_to_db(business, rooms, parsed_results)
        
        # Branch upsert 호출 확인
        upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
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
                "recommend_capacity_range": None,
                "price_config": price_cfg,
                "base_capacity": None,
                "extra_charge": None,
                "requires_call_on_sameday": False
            }
        }
        
        await service._save_to_db(business, rooms, parsed_results)
        
        upsert_call = mock_supabase._room_table.upsert.call_args_list[-1]
        room_data = upsert_call[0][0]
        
        assert room_data["price_config"] == price_cfg

    @pytest.mark.asyncio
    async def test_branch_upsert_does_not_overwrite_coordinates_with_null(self, service, mock_supabase):
        """coordinates가 없으면 branch upsert payload에 lat/lng를 넣지 않는다."""
        business = {"businessId": "biz1", "businessDisplayName": "Test Branch", "coordinates": None}
        rooms = [{"bizItemId": "r1", "name": "Room 1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}

        await service._save_to_db(business, rooms, parsed_results)

        upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
        branch_data = upsert_call[0][0]

        assert "lat" not in branch_data
        assert "lng" not in branch_data

    @pytest.mark.asyncio
    async def test_branch_upsert_saves_phone_number_from_business_payload(self, service, mock_supabase):
        """business.phoneInformationJson에서 대표 전화번호를 추출해 저장한다."""
        business = {
            "businessId": "biz1",
            "businessDisplayName": "Test Branch",
            "coordinates": None,
            "phoneInformationJson": {"phoneNumber": "02-123-4567"},
        }
        rooms = [{"bizItemId": "r1", "name": "Room 1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}

        await service._save_to_db(business, rooms, parsed_results)

        upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
        branch_data = upsert_call[0][0]

        assert branch_data["phone_number"] == "02-123-4567"

    @pytest.mark.asyncio
    async def test_branch_upsert_saves_phone_number_from_room_payload_fallback(self, service, mock_supabase):
        """business에 전화번호가 없으면 room.phone을 fallback으로 사용한다."""
        business = {"businessId": "biz1", "businessDisplayName": "Test Branch", "coordinates": None}
        rooms = [
            {
                "bizItemId": "r1",
                "name": "Room 1",
                "phone": "010-1234-5678",
                "bizItemResources": [],
                "minMaxPrice": {"minPrice": 15000},
            }
        ]
        parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}

        await service._save_to_db(business, rooms, parsed_results)

        upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
        branch_data = upsert_call[0][0]

        assert branch_data["phone_number"] == "010-1234-5678"

    @pytest.mark.asyncio
    async def test_branch_upsert_extracts_phone_from_booking_precaution_text(self, service, mock_supabase):
        """room 예약 주의사항 텍스트에서 전화번호를 fallback 추출한다."""
        business = {"businessId": "biz1", "businessDisplayName": "Test Branch", "coordinates": None}
        rooms = [
            {
                "bizItemId": "r1",
                "name": "Room 1",
                "desc": "당일 예약 문의 필수",
                "bookingPrecautionJson": [
                    {
                        "title": None,
                        "desc": "입금 계좌 3333134566206 / 문의 0507-1343-7985",
                    }
                ],
                "bizItemResources": [],
                "minMaxPrice": {"minPrice": 15000},
            }
        ]
        parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}

        await service._save_to_db(business, rooms, parsed_results)

        upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
        branch_data = upsert_call[0][0]
        assert branch_data["phone_number"] == "0507-1343-7985"

    @pytest.mark.asyncio
    async def test_branch_upsert_uses_source_hint_phone_fallback(self, service, mock_supabase):
        """business/room에 번호가 없으면 map source_hint의 번호를 fallback으로 사용한다."""
        business = {"businessId": "biz1", "businessDisplayName": "Test Branch", "coordinates": None}
        rooms = [{"bizItemId": "r1", "name": "Room 1", "bizItemResources": [], "minMaxPrice": {"minPrice": 15000}}]
        parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}
        source_hint = {"id": "biz1", "name": "테스트 합주실", "phone": "02-123-4567"}

        await service._save_to_db(business, rooms, parsed_results, source_hint=source_hint)

        upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
        branch_data = upsert_call[0][0]
        assert branch_data["phone_number"] == "02-123-4567"

    @pytest.mark.asyncio
    async def test_branch_upsert_ignores_resource_url_numeric_noise(self, service, mock_supabase):
        """resourceUrl timestamp-like digits must not be treated as phone number."""
        business = {"businessId": "biz1", "businessDisplayName": "Test Branch", "coordinates": None}
        rooms = [
            {
                "bizItemId": "r1",
                "name": "Room 1",
                "desc": "전화번호 보기",
                "bizItemResources": [
                    {"resourceUrl": "https://foo.cdn.net/20251005_152/17596265723914UtbY_JPEG/8705"}
                ],
                "minMaxPrice": {"minPrice": 15000},
            }
        ]
        parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}

        await service._save_to_db(business, rooms, parsed_results)

        upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
        branch_data = upsert_call[0][0]
        assert "phone_number" not in branch_data

    @pytest.mark.asyncio
    async def test_branch_upsert_prefers_real_phone_over_resource_url_noise(self, service, mock_supabase):
        """When both exist, real contact number in text should win."""
        business = {"businessId": "biz1", "businessDisplayName": "Test Branch", "coordinates": None}
        rooms = [
            {
                "bizItemId": "r1",
                "name": "Room 1",
                "bookingPrecautionJson": [{"desc": "문의 0507-1461-8067"}],
                "bizItemResources": [
                    {"resourceUrl": "https://foo.cdn.net/20251005_152/17596265723914UtbY_JPEG/8705"}
                ],
                "minMaxPrice": {"minPrice": 15000},
            }
        ]
        parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}

        await service._save_to_db(business, rooms, parsed_results)

        upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
        branch_data = upsert_call[0][0]
        assert branch_data["phone_number"] == "0507-1461-8067"

    @pytest.mark.asyncio
    async def test_branch_upsert_uses_place_click_phone_fallback(self, service, mock_supabase):
        """When GraphQL/source text has no phone, place click fallback should fill phone_number."""
        service.map_crawler.reveal_phone_number = AsyncMock(return_value="010-3032-6033")
        business = {"businessId": "biz1", "businessDisplayName": "Test Branch", "coordinates": None}
        rooms = [
            {
                "bizItemId": "r1",
                "name": "Room 1",
                "desc": "전화번호 보기",
                "bizItemResources": [],
                "minMaxPrice": {"minPrice": 15000},
            }
        ]
        parsed_results = {"r1": {"max_capacity": 4, "recommend_capacity": 2}}
        source_hint = {"id": "biz1", "name": "Test Branch", "placeId": "1770803230"}

        await service._save_to_db(business, rooms, parsed_results, source_hint=source_hint)

        upsert_call = mock_supabase._branch_table.upsert.call_args_list[0]
        branch_data = upsert_call[0][0]
        assert branch_data["phone_number"] == "010-3032-6033"
        service.map_crawler.reveal_phone_number.assert_awaited_once_with("1770803230")

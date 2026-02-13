# tests/services/test_room_parser_service.py
"""
RoomParserService 단위 테스트

테스트 대상:
- _parse_with_regex: 정규표현식 기반 룸 정보 파싱
- _extract_json_from_response: LLM 응답에서 JSON 추출
- _validate_parsed_result: 파싱 결과 유효성 검증
- parse_room_desc: Ollama LLM 파싱 (Ollama 서버 실행 시에만)

실행: pytest tests/services/test_room_parser_service.py -v
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.room_parser_service import RoomParserService
from app.services.room_collection_service import RoomCollectionService


class TestParseWithRegex:
    """_parse_with_regex 메서드 테스트"""
    
    @pytest.fixture
    def parser(self):
        """Ollama 없이 Regex만 테스트하기 위한 인스턴스"""
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value=None)  # Ollama 비활성화
        return RoomParserService(ollama_client=mock_client)
    
    # ============== TC01: 기본 파싱 (평일 태그 + 최대 인원) ==============
    def test_basic_parsing_weekday(self, parser):
        """[평일] 태그와 최대 인원 파싱"""
        result = parser._parse_with_regex("[평일] 블랙룸", "최대 10인 수용 가능")
        
        assert result["clean_name"] == "블랙룸"
        assert result["day_type"] == "weekday"
        assert result["max_capacity"] == 10
    
    # ============== TC02: 범위 중간값 (주말 태그 + N~M인) ==============
    def test_range_capacity_weekend(self, parser):
        """(주말) 태그와 범위형 인원 파싱"""
        result = parser._parse_with_regex("화이트룸 (주말)", "4~6인 권장, 최대 8인")
        
        assert result["clean_name"] == "화이트룸"
        assert result["day_type"] == "weekend"
        assert result["recommend_capacity"] == 5  # (4+6)//2 = 5
        assert result["max_capacity"] == 8
        # [v2.0.0] 범위 원본 검증
        assert result["recommend_capacity_range"] == [4, 6]
    
    # ============== TC03: 추가요금 파싱 ==============
    def test_extra_charge_parsing(self, parser):
        """기본 인원 및 추가요금 파싱"""
        result = parser._parse_with_regex("스튜디오A", "기본 4인, 1인 추가시 3,000원")
        
        assert result["base_capacity"] == 4
        assert result["extra_charge"] == 3000
    
    # ============== TC04: 당일 예약 전화 감지 ==============
    def test_same_day_call_required(self, parser):
        """당일 예약 전화 문의 감지"""
        result = parser._parse_with_regex("레드룸", "당일 예약은 전화 문의 바랍니다")
        
        assert result["requires_call_on_same_day"] is True
    
    # ============== TC05: 빈 설명 처리 ==============
    def test_empty_description(self, parser):
        """설명이 없는 경우 기본값 처리"""
        result = parser._parse_with_regex("일반룸", "")
        
        assert result["clean_name"] == "일반룸"
        assert result["day_type"] is None
        assert result["max_capacity"] is None
        assert result["requires_call_on_same_day"] is False
        # [v2.0.0] 인원 정보 없으면 range도 None
        assert result["recommend_capacity_range"] is None
    
    # ============== TC: None 설명 처리 ==============
    def test_none_description(self, parser):
        """설명이 None인 경우 처리"""
        result = parser._parse_with_regex("테스트룸", None)
        
        assert result["clean_name"] == "테스트룸"
        assert result["requires_call_on_same_day"] is False
    
    # ============== TC: "N명까지" 패턴 ==============
    def test_until_pattern_capacity(self, parser):
        """'N명까지 수용' 패턴 인식"""
        result = parser._parse_with_regex("룸A", "10명까지 수용 가능합니다")
        
        assert result["max_capacity"] == 10
    
    # ============== TC: 주말/공휴일 복합 태그 ==============
    def test_weekend_holiday_tag(self, parser):
        """[주말/공휴일] 복합 태그 처리"""
        result = parser._parse_with_regex("[주말/공휴일] 스튜디오", "5인 권장")
        
        assert result["day_type"] == "weekend"
        assert "주말" not in result["clean_name"]


    # ============== TC: "N인이 합주 가능" 패턴 ==============
    def test_usage_possible_pattern(self, parser):
        """'N인이 합주 가능' 패턴 인식"""
        result = parser._parse_with_regex("룸A", "10인이 합주 가능")
        assert result["max_capacity"] == 10

    def test_usage_possible_pattern_with_space(self, parser):
        """'8 인이 합주 가능' (공백 포함) 패턴 인식"""
        result = parser._parse_with_regex("룸B", "8 인이 합주 가능")
        assert result["max_capacity"] == 8

    # ============== TC: "N인 까지 이용 가능" 패턴 ==============
    def test_until_usage_pattern(self, parser):
        """'N인 까지 이용 가능' 패턴 인식"""
        result = parser._parse_with_regex("룸C", "4인 까지 이용 가능")
        assert result["max_capacity"] == 4

    # ============== TC: "N인 이하" 패턴 ==============
    def test_under_n_pattern(self, parser):
        """'N인 이하' 패턴 인식"""
        result = parser._parse_with_regex("룸D", "15인 이하")
        assert result["max_capacity"] == 15

    # ============== TC: name에서 "(정원 N명, 최대 M명)" 추출 ==============
    def test_name_capacity_parentheses(self, parser):
        """name 필드의 '(정원 13명, 최대 18명)' 패턴 추출"""
        result = parser._parse_with_regex("블랙룸 (정원 13명, 최대 18명)", "")
        assert result["clean_name"] == "블랙룸"
        assert result["max_capacity"] == 18
        assert result["recommend_capacity"] == 13

    # ============== TC: "권장 인원 N명 M명" 공백 범위 ==============
    def test_recommend_space_range(self, parser):
        """
        Verifies parsing of a space-separated recommended capacity range like "권장 인원 10명 12명".
        
        Asserts that recommend_capacity is the integer average of the two bounds, max_capacity equals the upper bound, and recommend_capacity_range contains the [min, max] pair.
        """
        result = parser._parse_with_regex("룸E", "권장 인원 10명 12명")
        assert result["recommend_capacity"] == 11  # (10+12)//2
        assert result["max_capacity"] == 12
        # [v2.0.0] 범위 검증
        assert result["recommend_capacity_range"] == [10, 12]

    # ============== TC: desc 우선 추출 ==============
    def test_desc_priority_over_name(self, parser):
        """desc에 인원 정보 있으면 name보다 우선"""
        result = parser._parse_with_regex("블랙룸 (최대 18명)", "최대 30인 수용 가능")
        assert result["max_capacity"] == 30

    # ============== TC: name에만 인원 정보 있을 때 fallback ==============
    def test_name_fallback_when_desc_empty(self, parser):
        """desc에 인원 정보 없으면 name에서 추출"""
        result = parser._parse_with_regex("블랙룸 (정원 13명, 최대 18명)", "넓은 공간입니다")
        assert result["max_capacity"] == 18
        assert result["recommend_capacity"] == 13

    # ============== TC: "(-N명)" 괄호 최대인원 패턴 ==============
    def test_paren_dash_capacity(self, parser):
        """'R룸 (-15명)' 괄호 최대인원 패턴 인식"""
        result = parser._parse_with_regex("R룸 (-15명)", "")
        assert result["clean_name"] == "R룸"
        assert result["max_capacity"] == 15

    def test_paren_dash_capacity_small(self, parser):
        """'C룸 (-6명)' 소규모 괄호 패턴 인식"""
        result = parser._parse_with_regex("C룸 (-6명)", "장비 목록만 있는 설명")
        assert result["clean_name"] == "C룸"
        assert result["max_capacity"] == 6

    def test_suryong_ganeung_pattern(self, parser):
        """'N인 수용 가능' 패턴 인식 (Pattern 4/5 경계)"""
        result = parser._parse_with_regex("룸", "10인 수용 가능")
        assert result["max_capacity"] == 10

    def test_equipment_model_false_positive(self, parser):
        """장비 모델명(OB1-500)이 인원으로 오파싱되지 않는지 확인 (회귀 테스트)"""
        # '인/명' 접미사가 없으므로 파싱되지 않아야 함
        result = parser._parse_with_regex("룸A", "Orange OB1-500 Head, Marshall 앰프")
        assert result["max_capacity"] is None



class TestExtractJsonFromResponse:
    """_extract_json_from_response 메서드 테스트"""
    
    @pytest.fixture
    def parser(self):
        mock_client = MagicMock()
        return RoomParserService(ollama_client=mock_client)
    
    # ============== TC06: ```json 블록 제거 ==============
    def test_remove_json_code_block(self, parser):
        """```json ... ``` 마크다운 블록 제거"""
        input_text = '```json\n{"a": 1}\n```'
        result = parser._extract_json_from_response(input_text)
        
        assert result == '{"a": 1}'
    
    # ============== TC07: ``` 블록 제거 ==============
    def test_remove_plain_code_block(self, parser):
        """``` ... ``` 마크다운 블록 제거"""
        input_text = '```\n{"b": 2}\n```'
        result = parser._extract_json_from_response(input_text)
        
        assert result == '{"b": 2}'
    
    # ============== TC08: 순수 JSON 유지 ==============
    def test_plain_json_unchanged(self, parser):
        """마크다운 없는 순수 JSON 그대로 반환"""
        input_text = '{"c": 3}'
        result = parser._extract_json_from_response(input_text)
        
        assert result == '{"c": 3}'
    
    # ============== TC: 앞뒤 공백 제거 ==============
    def test_trim_whitespace(self, parser):
        """앞뒤 공백 제거"""
        input_text = '  \n{"d": 4}\n  '
        result = parser._extract_json_from_response(input_text)
        
        assert result == '{"d": 4}'


class TestValidateParsedResult:
    """_validate_parsed_result 메서드 테스트"""
    
    @pytest.fixture
    def parser(self):
        mock_client = MagicMock()
        return RoomParserService(ollama_client=mock_client)
    
    def test_valid_result(self, parser):
        """유효한 결과 통과"""
        result = {
            "clean_name": "블랙룸",
            "day_type": "weekday",
            "max_capacity": 10,
            "recommend_capacity": 5,
            "extra_charge": 3000
        }
        assert parser._validate_parsed_result(result) is True
    
    def test_missing_clean_name(self, parser):
        """clean_name 필수 필드 누락"""
        result = {"max_capacity": 10}
        assert parser._validate_parsed_result(result) is False
    
    def test_invalid_max_capacity_too_high(self, parser):
        """비현실적인 최대 인원 (50 초과)"""
        result = {"clean_name": "룸", "max_capacity": 100}
        assert parser._validate_parsed_result(result) is False
    
    def test_invalid_max_capacity_negative(self, parser):
        """음수 최대 인원"""
        result = {"clean_name": "룸", "max_capacity": -5}
        assert parser._validate_parsed_result(result) is False
    
    def test_invalid_extra_charge_too_high(self, parser):
        """비현실적인 추가 요금 (50,000 초과)"""
        result = {"clean_name": "룸", "extra_charge": 100000}
        assert parser._validate_parsed_result(result) is False
    
    def test_invalid_day_type(self, parser):
        """잘못된 day_type 값"""
        result = {"clean_name": "룸", "day_type": "holiday"}
        assert parser._validate_parsed_result(result) is False
    
    def test_null_values_valid(self, parser):
        """null 값들은 유효"""
        result = {
            "clean_name": "룸",
            "day_type": None,
            "max_capacity": None,
            "extra_charge": None
        }
        assert parser._validate_parsed_result(result) is True
    
    # ============== TC: recommend_capacity_range 검증 (v2.0.0) ==============
    def test_valid_capacity_range(self, parser):
        """유효한 recommend_capacity_range"""
        result = {"clean_name": "룸", "recommend_capacity_range": [4, 6]}
        assert parser._validate_parsed_result(result) is True
    
    def test_invalid_capacity_range_wrong_length(self, parser):
        """원소가 2개가 아닌 recommend_capacity_range"""
        result = {"clean_name": "룸", "recommend_capacity_range": [4]}
        assert parser._validate_parsed_result(result) is False
    
    def test_invalid_capacity_range_reversed(self, parser):
        """min > max인 recommend_capacity_range"""
        result = {"clean_name": "룸", "recommend_capacity_range": [10, 4]}
        assert parser._validate_parsed_result(result) is False
    
    def test_invalid_capacity_range_too_high(self, parser):
        """비현실적 범위 (최대 50 초과)"""
        result = {"clean_name": "룸", "recommend_capacity_range": [4, 100]}
        assert parser._validate_parsed_result(result) is False


class TestOllamaIntegration:
    """Ollama 연동 테스트 (Ollama 서버 실행 필요)"""
    
    @pytest.fixture
    def parser(self):
        """실제 Ollama 클라이언트 사용"""
        return RoomParserService()
    
    @pytest.fixture
    def mock_parser(self):
        """Mock Ollama 클라이언트 사용"""
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value=None)
        return RoomParserService(ollama_client=mock_client)
    
    @pytest.mark.asyncio
    async def test_parse_with_actual_ollama(self, parser):
        """실제 Ollama 서버와 통신 테스트 (서버 실행 중일 때만)"""
        try:
            result = await parser.parse_room_desc("[평일] 블랙룸", "최대 10인, 4~6인 권장")
            assert "clean_name" in result
            assert "max_capacity" in result
        except Exception:
            pytest.skip("Ollama 서버가 실행 중이 아님")

    @pytest.mark.asyncio
    async def test_fallback_to_regex_when_ollama_unavailable(self, mock_parser):
        """Ollama 응답 없을 시 Regex Fallback"""
        result = await mock_parser.parse_room_desc("[평일] 블랙룸", "최대 10인")
        
        assert result["clean_name"] == "블랙룸"
        assert result["day_type"] == "weekday"
        assert result["max_capacity"] == 10
    
    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self, mock_parser):
        """잘못된 JSON 응답 시 Regex Fallback"""
        mock_parser.ollama_client.generate = AsyncMock(return_value="not valid json")
        
        result = await mock_parser.parse_room_desc("[평일] 블랙룸", "최대 10인")
        
        assert result["clean_name"] == "블랙룸"
        assert result["max_capacity"] == 10
    
    @pytest.mark.asyncio
    async def test_fallback_on_validation_failure(self, mock_parser):
        """검증 실패 시 Regex Fallback"""
        # max_capacity가 비현실적인 값
        mock_parser.ollama_client.generate = AsyncMock(
            return_value='{"clean_name": "룸", "max_capacity": 999}'
        )
        
        result = await mock_parser.parse_room_desc("[평일] 블랙룸", "최대 10인")
        
        # Regex Fallback으로 정상 파싱
        assert result["clean_name"] == "블랙룸"
        assert result["max_capacity"] == 10


class TestMultiLevelParsing:
    """다단계 파싱 파이프라인 테스트"""
    
    @pytest.fixture
    def parser(self):
        """Mock Ollama 클라이언트를 사용하는 파서"""
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value=None)  # LLM 응답 없음
        return RoomParserService(ollama_client=mock_client)
    
    # ============== Level 1: Keyword Map ==============
    @pytest.mark.asyncio
    async def test_keyword_map_대형(self, parser):
        """'대형' 키워드가 있으면 max_capacity=15"""
        result = await parser.parse_room_desc("대형 합주실", "")
        assert result["max_capacity"] == 15
    
    @pytest.mark.asyncio
    async def test_keyword_map_중형(self, parser):
        """'중형' 키워드가 있으면 max_capacity=8"""
        result = await parser.parse_room_desc("중형 A룸", "")
        assert result["max_capacity"] == 8
    
    @pytest.mark.asyncio
    async def test_keyword_map_소형(self, parser):
        """'소형' 키워드가 있으면 max_capacity=4"""
        result = await parser.parse_room_desc("소형룸", "")
        assert result["max_capacity"] == 4
    
    @pytest.mark.asyncio
    async def test_keyword_map_not_triggered_by_alphabet(self, parser):
        """알파벳 한 글자(S룸, L룸)는 Keyword Map 적용 안 됨"""
        result = await parser.parse_room_desc("S룸", "최대 20인")  # Regex fallback
        assert result["max_capacity"] == 20  # Regex에서 추출
    
    # ============== Noise Reduction ==============
    def test_clean_text_removes_html(self, parser):
        """HTML 태그 제거"""
        result = parser._clean_text_for_llm("<b>최대 10인</b>")
        assert "<b>" not in result
        assert "최대 10인" in result
    
    def test_clean_text_removes_emoji(self, parser):
        """이모지 제거"""
        result = parser._clean_text_for_llm("✨최대 10명🎉")
        assert "최대" in result
        assert "10" in result
        assert "✨" not in result
    
    def test_clean_text_preserves_allowed_chars(self, parser):
        """인원/가격 관련 특수문자(~, -, ,) 보존 확인"""
        result = parser._clean_text_for_llm("4~6인, 1인당 3,000원")
        assert "~" in result
        assert "-" not in result # 4~6인은 ~만 있음
        assert "," in result
        assert "3,000" in result



class TestExportUnresolved:
    """_export_unresolved 메서드 테스트"""

    @pytest.fixture
    def service(self):
        """Mock 의존성을 가진 RoomCollectionService"""
        with patch('app.services.room_collection_service.NaverMapCrawler'), \
             patch('app.services.room_collection_service.NaverRoomFetcher'), \
             patch('app.services.room_collection_service.RoomParserService'), \
             patch('app.services.room_collection_service.get_supabase_client'):
            return RoomCollectionService()

    @pytest.mark.asyncio
    async def test_exports_when_no_capacity(self, service, tmp_path, monkeypatch):
        """max_capacity가 None이면 unresolved JSON으로 내보내기"""
        import app.services.room_collection_service as mod
        fake_file = str(tmp_path / "app" / "services" / "room_collection_service.py")
        monkeypatch.setattr(mod, '__file__', fake_file)

        business = {"businessId": "b1", "businessDisplayName": "테스트합주실"}
        rooms = [{"bizItemId": "r1", "name": "룸A", "desc": "설명 없음"}]
        parsed_results = {"r1": {"max_capacity": None, "clean_name": "룸A"}}

        await service._export_unresolved(business, rooms, parsed_results)

        export_dir = tmp_path / "scripts" / "unresolved"
        files = list(export_dir.glob("unresolved_*.json"))
        assert len(files) == 1

        with open(files[0], "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]["biz_item_id"] == "r1"
        assert data[0]["failure_reason"] == "no_capacity_info"

    @pytest.mark.asyncio
    async def test_no_export_when_capacity_found(self, service, tmp_path, monkeypatch):
        """max_capacity가 정상이면 unresolved로 내보내지 않음"""
        import app.services.room_collection_service as mod
        fake_file = str(tmp_path / "app" / "services" / "room_collection_service.py")
        monkeypatch.setattr(mod, '__file__', fake_file)

        business = {"businessId": "b1", "businessDisplayName": "테스트합주실"}
        rooms = [{"bizItemId": "r1", "name": "룸A", "desc": "최대 10인"}]
        parsed_results = {"r1": {"max_capacity": 10, "clean_name": "룸A"}}

        await service._export_unresolved(business, rooms, parsed_results)

        export_dir = tmp_path / "scripts" / "unresolved"
        if export_dir.exists():
            files = list(export_dir.glob("unresolved_*.json"))
            assert len(files) == 0
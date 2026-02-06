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

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.room_parser_service import RoomParserService


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

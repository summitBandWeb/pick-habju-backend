# tests/services/test_room_parser_service.py
"""
RoomParserService 단위 테스트

테스트 대상:
- _parse_with_regex: 정규표현식 기반 룸 정보 파싱
- _extract_json_from_response: LLM 응답에서 JSON 추출

실행: pytest tests/services/test_room_parser_service.py -v
"""

import pytest
from app.services.room_parser_service import RoomParserService


class TestParseWithRegex:
    """_parse_with_regex 메서드 테스트"""
    
    @pytest.fixture
    def parser(self):
        """API Key 없이 Regex만 테스트하기 위한 인스턴스"""
        return RoomParserService(api_key=None)
    
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
        return RoomParserService(api_key=None)
    
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

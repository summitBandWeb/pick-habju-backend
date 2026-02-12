"""
로깅 에지 케이스 테스트 모듈

Rationale:
    코드리뷰에서 지적된 "에지 케이스 테스트 부족" 문제를 해결합니다.
    LogMasker, SensitiveDataFilter, JsonFormatter의 경계값과 
    예외 상황을 집중적으로 검증합니다.
"""

import json
import logging
import pytest
from unittest.mock import patch
from app.core.logging_config import LogMasker, SensitiveDataFilter, JsonFormatter
from app.core.context import set_trace_id, trace_id_context


# =============================================================================
# LogMasker.mask_string 에지 케이스
# =============================================================================

class TestLogMaskerString:
    """
    LogMasker.mask_string 에지 케이스 테스트

    Rationale:
        다양한 입력 형식(빈 문자열, 민감 키 없음, 복수 키, JSON, URL 파라미터,
        헤더 형식)에 대해 마스킹이 올바르게 동작하는지 검증합니다.
    """

    def test_mask_string_empty(self):
        """빈 문자열 입력 시 에러 없이 빈 문자열이 반환되는지 검증"""
        result = LogMasker.mask_string("")
        assert result == ""

    def test_mask_string_no_sensitive(self):
        """민감 키가 없는 일반 문자열은 원본이 그대로 유지되는지 검증"""
        original = "일반적인 로그 메시지입니다. 2026-02-13 정상 동작."
        result = LogMasker.mask_string(original)
        assert result == original

    def test_mask_string_multiple_keys(self):
        """한 문자열에 여러 민감 키가 있을 때 모두 마스킹되는지 검증"""
        text = 'password=secret123 token=abc-token-456 email=user@test.com'
        result = LogMasker.mask_string(text)

        assert "secret123" not in result
        assert "abc-token-456" not in result
        assert "user@test.com" not in result
        assert "***" in result

    def test_mask_string_json_format(self):
        """JSON 포맷 문자열 내 민감 값이 마스킹되는지 검증"""
        text = '{"password": "my_secret_pass", "username": "john"}'
        result = LogMasker.mask_string(text)

        assert "my_secret_pass" not in result
        # NOTE: username은 민감 키가 아니므로 유지되어야 함
        assert "john" in result

    def test_mask_string_url_params(self):
        """URL 쿼리 파라미터 내 민감 값이 마스킹되는지 검증"""
        text = "https://api.example.com?token=eyJhbGciOiJ&user=test"
        result = LogMasker.mask_string(text)

        assert "eyJhbGciOiJ" not in result
        assert "***" in result
        # user 파라미터는 보존되어야 함
        assert "user=test" in result or "test" in result

    def test_mask_string_quoted_with_space(self):
        """따옴표로 감싸진 값 내부의 공백이 있어도 마스킹되는지 검증"""
        text = 'password="my secret value" token=\'another secret\''
        result = LogMasker.mask_string(text)
        
        assert "my secret value" not in result
        assert "another secret" not in result
        assert 'password="***"' in result or "password='***'" in result
        assert "token='***'" in result or 'token="***"' in result

    def test_mask_string_query_string_separator(self):
        """쿼리 스트링 구분자(&)가 있을 때 값만 정확히 마스킹되는지 검증"""
        text = "token=abc12345&user_id=999&auth=xyz"
        result = LogMasker.mask_string(text)
        
        assert "abc12345" not in result
        assert "xyz" not in result
        # user_id도 민감 키워드에 포함되어 있다면 마스킹됨 (SENSITIVE_KEYS 확인 필요)
        # 만약 user_id가 민감 키라면 999도 마스킹되어야 함
        if "user_id" in LogMasker.SENSITIVE_KEYS:
            assert "999" not in result
        
        # 구분자는 유지되어야 함 (구조 보존)
        assert "&" in result

    def test_mask_string_header_format(self):
        """HTTP 헤더 포맷(Authorization: Bearer xxx)이 마스킹되는지 검증"""
        text = "authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = LogMasker.mask_string(text)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "***" in result

    def test_mask_string_case_insensitive(self):
        """대소문자를 무시하고 마스킹이 적용되는지 검증"""
        text = 'PASSWORD=SuperSecret TOKEN=MyToken123'
        result = LogMasker.mask_string(text)

        assert "SuperSecret" not in result
        assert "MyToken123" not in result


# =============================================================================
# LogMasker.mask_dict 에지 케이스
# =============================================================================

class TestLogMaskerDict:
    """
    LogMasker.mask_dict 에지 케이스 테스트

    Rationale:
        dict 입력의 다양한 구조(중첩, 리스트 포함, 비-dict)에 대해
        재귀 마스킹이 정상 동작하는지 검증합니다.
    """

    def test_mask_dict_nested(self):
        """중첩 dict 내 민감 키가 재귀적으로 마스킹되는지 검증"""
        data = {
            "user": {
                "name": "John",
                "password": "secret123",
                "profile": {
                    "email": "john@test.com",
                    "age": 25,
                },
            }
        }
        result = LogMasker.mask_dict(data)

        assert result["user"]["password"] == "***"
        assert result["user"]["profile"]["email"] == "***"
        # NOTE: 민감 키가 아닌 값은 유지
        assert result["user"]["name"] == "John"
        assert result["user"]["profile"]["age"] == 25

    def test_mask_dict_with_list(self):
        """리스트 내 dict의 민감 키도 마스킹되는지 검증"""
        data = {
            "users": [
                {"name": "Alice", "token": "tok-111"},
                {"name": "Bob", "token": "tok-222"},
            ]
        }
        result = LogMasker.mask_dict(data)

        assert result["users"][0]["token"] == "***"
        assert result["users"][1]["token"] == "***"
        assert result["users"][0]["name"] == "Alice"
        assert result["users"][1]["name"] == "Bob"

    def test_mask_dict_non_dict_input(self):
        """비-dict 입력(int, str 등)이 원본 그대로 반환되는지 검증"""
        assert LogMasker.mask_dict(42) == 42
        assert LogMasker.mask_dict("hello") == "hello"
        assert LogMasker.mask_dict(None) is None
        assert LogMasker.mask_dict(True) is True

    def test_mask_dict_empty(self):
        """빈 dict가 에러 없이 빈 dict로 반환되는지 검증"""
        result = LogMasker.mask_dict({})
        assert result == {}

    def test_mask_dict_empty_list(self):
        """빈 리스트가 에러 없이 빈 리스트로 반환되는지 검증"""
        result = LogMasker.mask_dict([])
        assert result == []


# =============================================================================
# SensitiveDataFilter 에지 케이스
# =============================================================================

class TestSensitiveDataFilter:
    """
    SensitiveDataFilter 에지 케이스 테스트

    Rationale:
        로그 레코드의 msg가 dict/str 등 다양한 타입일 때 
        필터가 올바르게 마스킹하고, trace_id를 정확히 주입하는지 검증합니다.
    """

    def setup_method(self):
        """각 테스트 전 filter 인스턴스 생성"""
        self.filter = SensitiveDataFilter()

    def _make_record(self, msg, level=logging.INFO):
        """테스트용 LogRecord 생성 헬퍼"""
        record = logging.LogRecord(
            name="test",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=None,
            exc_info=None,
        )
        return record

    def test_sensitive_filter_dict_msg(self):
        """dict 메시지가 전달될 때 민감 키가 마스킹되는지 검증"""
        record = self._make_record({"password": "1234", "action": "login"})
        self.filter.filter(record)

        assert record.msg["password"] == "***"
        assert record.msg["action"] == "login"

    def test_sensitive_filter_string_msg(self):
        """문자열 메시지 내 민감 정보가 마스킹되는지 검증"""
        record = self._make_record('User login: password=secret api_key=abc')
        self.filter.filter(record)

        assert "secret" not in record.msg
        assert "abc" not in record.msg

    def test_sensitive_filter_trace_id_injection(self):
        """filter 호출 후 record.trace_id가 정상 주입되는지 검증"""
        # NOTE: 테스트 환경에서 ContextVar를 직접 설정
        token = trace_id_context.set("test-trace-999")
        try:
            record = self._make_record("simple log")
            self.filter.filter(record)

            assert record.trace_id == "test-trace-999"
        finally:
            trace_id_context.reset(token)

    def test_sensitive_filter_no_trace_id(self):
        """trace_id가 설정되지 않은 경우 None이 주입되는지 검증"""
        token = trace_id_context.set(None)
        try:
            record = self._make_record("simple log")
            self.filter.filter(record)

            assert record.trace_id is None
        finally:
            trace_id_context.reset(token)

    def test_sensitive_filter_returns_true(self):
        """필터가 항상 True를 반환하여 로그가 누락되지 않는지 검증"""
        record = self._make_record("any message")
        result = self.filter.filter(record)
        assert result is True


# =============================================================================
# JsonFormatter 에지 케이스
# =============================================================================

class TestJsonFormatter:
    """
    JsonFormatter 에지 케이스 테스트

    Rationale:
        JSON 포맷터가 기본 필드 구조, extra 데이터 마스킹, 
        trace_id 포함을 올바르게 처리하는지 검증합니다.
    """

    def setup_method(self):
        """각 테스트 전 formatter 인스턴스 생성"""
        self.formatter = JsonFormatter()

    def _make_record(self, msg, level=logging.INFO, **extra):
        """테스트용 LogRecord 생성 헬퍼

        Args:
            msg: 로그 메시지 (str 또는 dict)
            level: 로그 레벨
            **extra: 추가 속성 (extra 데이터로 주입)
        """
        record = logging.LogRecord(
            name="test.logger",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=None,
            exc_info=None,
        )
        # extra 데이터 주입
        for k, v in extra.items():
            setattr(record, k, v)
        # trace_id 기본값 설정
        if not hasattr(record, "trace_id"):
            record.trace_id = None
        return record

    def test_json_formatter_basic_structure(self):
        """JSON 출력에 필수 필드(timestamp, level, logger, message)가 존재하는지 검증"""
        record = self._make_record("테스트 메시지")
        output = self.formatter.format(record)
        parsed = json.loads(output)

        assert "timestamp" in parsed
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["message"] == "테스트 메시지"

    def test_json_formatter_extra_masking(self):
        """extra 데이터에 민감 키가 포함될 때 마스킹되어 출력되는지 검증"""
        record = self._make_record(
            "요청 처리",
            api_key="super-secret-key-123",
            request_path="/api/v1/rooms",
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)

        # NOTE: api_key는 민감 키이므로 마스킹 필요
        assert parsed.get("api_key") == "***"
        # 비민감 키는 원본 유지
        assert parsed.get("request_path") == "/api/v1/rooms"

    def test_json_formatter_with_trace_id(self):
        """trace_id가 JSON 출력에 포함되는지 검증"""
        record = self._make_record("trace test")
        record.trace_id = "fmt-trace-abc-123"
        output = self.formatter.format(record)
        parsed = json.loads(output)

        assert parsed["trace_id"] == "fmt-trace-abc-123"

    def test_json_formatter_dict_message(self):
        """msg가 dict일 때 JSON 구조에 올바르게 병합되는지 검증"""
        record = self._make_record({"event": "room_reserved", "room_id": 42})
        output = self.formatter.format(record)
        parsed = json.loads(output)

        assert parsed["event"] == "room_reserved"
        assert parsed["room_id"] == 42
        assert parsed["level"] == "INFO"

    def test_json_formatter_unicode(self):
        """한글 등 유니코드 메시지가 올바르게 출력되는지 검증"""
        record = self._make_record("합주실 예약이 완료되었습니다 🎸")
        output = self.formatter.format(record)
        parsed = json.loads(output)

        assert "합주실 예약이 완료되었습니다" in parsed["message"]
        assert "🎸" in parsed["message"]

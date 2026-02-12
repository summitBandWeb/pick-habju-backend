import logging
import json
import pytest
from io import StringIO
from app.core.logging_config import LogMasker, SensitiveDataFilter, JsonFormatter
from app.core.context import set_trace_id

class TestLogMasker:
    """LogMasker 클래스의 마스킹 로직 테스트"""

    def test_mask_dict_simple(self):
        """단순 딕셔너리 내 민감 키 마스킹"""
        data = {
            "user": "tester",
            "password": "secret_password",
            "token": "sensitive_token",
            "api_key": "12345"
        }
        masked = LogMasker.mask_dict(data)
        
        assert masked["user"] == "tester"
        assert masked["password"] == "***"
        assert masked["token"] == "***"
        assert masked["api_key"] == "***"

    def test_mask_dict_nested(self):
        """중첩된 딕셔너리 및 리스트 내 민감 키 마스킹"""
        data = {
            "meta": {"env": "prod"},
            "payload": {
                "user": "admin",
                "auth": {
                    "access_token": "jwt_token_value",
                    "refresh_token": "refresh_value"
                },
                "history": [
                    {"action": "login", "secret": "hide_me"},
                    {"action": "logout"}
                ]
            }
        }
        masked = LogMasker.mask_dict(data)
        
        assert masked["payload"]["auth"]["access_token"] == "***"
        assert masked["payload"]["auth"]["refresh_token"] == "***"
        assert masked["payload"]["history"][0]["secret"] == "***"
        assert masked["payload"]["history"][0]["action"] == "login"

    def test_mask_string(self):
        """문자열 내 민감 패턴 마스킹 (Query String, Log Message 등)"""
        # Case 1: Key=Value 형식
        text1 = "Connecting with api_key=123456 and token=abcdefg"
        masked1 = LogMasker.mask_string(text1)
        assert "api_key=***" in masked1
        assert "token=***" in masked1
        
        # Case 2: Key:Value 형식
        text2 = "User login failed. password: my_password_123"
        masked2 = LogMasker.mask_string(text2)
        assert "password:***" in masked2 or "password=***" in masked2 # Regex치환 결과에 따라 다를 수 있음

    def test_mask_case_insensitive(self):
        """대소문자 구분 없이 마스킹"""
        data = {"PASSWORD": "secret", "Api_Key": "1234"}
        masked = LogMasker.mask_dict(data)
        assert masked["PASSWORD"] == "***"
        assert masked["Api_Key"] == "***"


class TestLoggingIntegration:
    """로깅 시스템(Formatter, Filter) 통합 테스트"""

    @pytest.fixture
    def logger_fixture(self):
        """테스트용 로거 및 캡처 스트림 설정"""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        handler.addFilter(SensitiveDataFilter())
        
        logger = logging.getLogger("test_security_logger")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        
        return logger, stream

    def test_trace_id_injection(self, logger_fixture):
        """로그에 Trace ID가 주입되는지 확인"""
        logger, stream = logger_fixture
        
        test_trace_id = "test-trace-uuid-1234"
        set_trace_id(test_trace_id)
        
        logger.info("Test message")
        
        log_output = stream.getvalue()
        log_json = json.loads(log_output)
        
        assert log_json.get("trace_id") == test_trace_id
        assert log_json.get("message") == "Test message"

    def test_extra_data_masking(self, logger_fixture):
        """extra로 전달된 데이터도 마스킹되는지 확인"""
        logger, stream = logger_fixture
        
        logger.info("User action", extra={
            "user_id": 1,
            "password": "raw_password",
            "metadata": {"token": "jwt_token"}
        })
        
        log_output = stream.getvalue()
        log_json = json.loads(log_output)
        
        assert log_json.get("password") == "***"
        assert log_json.get("metadata", {}).get("token") == "***"
        assert log_json.get("user_id") == 1

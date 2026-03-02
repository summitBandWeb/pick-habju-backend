import logging
from unittest.mock import patch
import pytest

from app.core import config

@pytest.fixture
def reset_warnings_emitted():
    """테스트 전후로 _WARNINGS_EMITTED 플래그를 초기화하는 픽스처"""
    original_state = config._WARNINGS_EMITTED
    config._WARNINGS_EMITTED = False
    yield
    config._WARNINGS_EMITTED = original_state

class TestStartupWarnings:
    """emit_startup_warnings() 함수에 대한 격리된 단위 테스트"""

    @patch("app.core.config._MISSING_CRAWLER_VARS", new_callable=list)
    def test_emit_warnings_all_missing(self, mock_missing_vars, caplog, reset_warnings_emitted):
        """모든 4개 변수 누락 시 모두 경고에 나타나는지 검증"""
        mock_missing_vars.extend(["GROOVE_BASE_URL", "DREAM_BASE_URL", "LOGIN_ID", "LOGIN_PW"])
        
        with caplog.at_level(logging.WARNING):
            config.emit_startup_warnings()
            
        assert len(caplog.records) == 1
        warning_msg = caplog.records[0].getMessage()
        assert "GROOVE_BASE_URL" in warning_msg
        assert "DREAM_BASE_URL" in warning_msg
        assert "LOGIN_ID" in warning_msg
        assert "LOGIN_PW" in warning_msg

    @patch("app.core.config._MISSING_CRAWLER_VARS", new_callable=list)
    def test_emit_warnings_some_missing(self, mock_missing_vars, caplog, reset_warnings_emitted):
        """일부 변수만 누락 시 해당 변수만 경고에 나타나는지 검증"""
        mock_missing_vars.extend(["GROOVE_BASE_URL"])
        
        with caplog.at_level(logging.WARNING):
            config.emit_startup_warnings()
            
        assert len(caplog.records) == 1
        warning_msg = caplog.records[0].getMessage()
        assert "GROOVE_BASE_URL" in warning_msg
        assert "DREAM_BASE_URL" not in warning_msg

    @patch("app.core.config._MISSING_CRAWLER_VARS", new_callable=list)
    def test_emit_warnings_none_missing(self, mock_missing_vars, caplog, reset_warnings_emitted):
        """모든 변수 설정(누락 없음) 시 경고가 출력되지 않는지 검증"""
        mock_missing_vars.clear()
        
        with caplog.at_level(logging.WARNING):
            config.emit_startup_warnings()
            
        assert len(caplog.records) == 0

    @patch("app.core.config._MISSING_CRAWLER_VARS", new_callable=list)
    def test_emit_warnings_idempotency(self, mock_missing_vars, caplog, reset_warnings_emitted):
        """emit_startup_warnings() 중복 호출 시 경고가 한 번만 출력되는지 검증"""
        mock_missing_vars.append("LOGIN_ID")
        
        with caplog.at_level(logging.WARNING):
            # 두 번 호출
            config.emit_startup_warnings()
            config.emit_startup_warnings()
            
        # 레코드는 1개만 있어야 함 (멱등성 가드 검증)
        assert len(caplog.records) == 1


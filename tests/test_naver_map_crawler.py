import pytest
import sys
from unittest.mock import MagicMock, patch
from app.crawler.naver_map_crawler import NaverMapCrawler

def test_search_sync_integration():
    """_search_sync 내부 동기 실행 흐름 검증 (Playwright & Dependencies Mock)"""
    crawler = NaverMapCrawler(headless=True)
    
    # playwright_stealth 모듈이 없을 경우를 대비해 sys.modules에 mock 추가
    mock_stealth_module = MagicMock()
    with patch.dict('sys.modules', {'playwright_stealth': mock_stealth_module}):
        with patch('app.crawler.naver_map_crawler.sync_playwright') as mock_pw, \
             patch('app.crawler.naver_map_crawler.UserAgent') as mock_ua_class:
            
            # 1. Setup Mock UserAgent
            mock_ua_instance = MagicMock()
            mock_ua_instance.random = "Test-UA"
            mock_ua_class.return_value = mock_ua_instance
            
            # 2. Setup Mock Playwright
            mock_p = MagicMock()
            mock_browser = MagicMock()
            mock_context = MagicMock()
            mock_page = MagicMock()
            
            mock_pw.return_value.__enter__.return_value = mock_p
            mock_p.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            
            # 3. Setup Extract Apollo State Mock
            with patch.object(
                crawler,
                '_extract_apollo_state_sync',
                return_value=[{"id": "123", "bookingBusinessId": "123", "name": "Test Room"}],
            ) as mock_extract:
                
                results = crawler._search_sync("test_query")
                
                # 검증
                assert len(results) == 1
                assert results[0]["id"] == "123"
                
                # UserAgent 호출 확인
                mock_ua_class.assert_called()
                
                # Browser Context 생성 시 UA 전달 확인
                call_args = mock_browser.new_context.call_args
                assert call_args.kwargs['user_agent'] == "Test-UA"
                
                # Stealth 적용 확인 (mock_stealth_module.stealth_sync 호출 확인)
                mock_stealth_module.stealth_sync.assert_called_once_with(mock_context)
                
                # Apollo State 추출 확인
                mock_extract.assert_called()

def test_extract_apollo_state_sync_mock():
    """evaluate를 통한 Apollo State 추출 로직 검증 (Mock Page)"""
    crawler = NaverMapCrawler()
    mock_page = MagicMock()
    mock_page.evaluate.return_value = [{"id": "999", "name": "Mocked Room"}]
    
    result = crawler._extract_apollo_state_sync(mock_page)
    
    assert result == [{"id": "999", "name": "Mocked Room"}]
    mock_page.evaluate.assert_called_once()

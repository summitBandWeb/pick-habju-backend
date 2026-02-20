import pytest
import sys
from unittest.mock import MagicMock, patch
from app.crawler.naver_map_crawler import NaverMapCrawler

def test_search_sync_integration():
    """_search_sync 내부에서 헬퍼 메서드들이 호출되는지 통합 검증"""
    crawler = NaverMapCrawler(headless=True)
    
    with patch('app.crawler.naver_map_crawler.sync_playwright') as mock_pw, \
         patch('app.crawler.naver_map_crawler.UserAgent') as mock_ua_class, \
         patch('playwright_stealth.stealth_sync', create=True) as mock_stealth_sync:
        
        mock_ua_instance = MagicMock()
        mock_ua_instance.random = "Test-UA"
        mock_ua_class.return_value = mock_ua_instance

        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        
        mock_pw.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        
        # 내부 메서드 Mocking (실제 로직 실행 방지)
        with patch.object(crawler, '_extract_apollo_state_sync', return_value=[]):
            
            crawler._search_sync("test_query")
            
            # 1. Context 생성 시 UA 전달 확인
            call_args = mock_browser.new_context.call_args
            assert call_args.kwargs['user_agent'] == "Test-UA"
            
            # 2. Stealth 로직 (Playwright) 호출 확인
            assert mock_stealth_sync.call_count == 1
            mock_stealth_sync.assert_called_with(mock_context)

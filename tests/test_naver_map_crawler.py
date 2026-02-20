import pytest
import sys
from unittest.mock import MagicMock, patch
from app.crawler.naver_map_crawler import NaverMapCrawler

# Fixture to simulate missing dependencies
@pytest.fixture
def mock_missing_packages():
    with patch('app.crawler.naver_map_crawler.UserAgent', None), \
         patch('app.crawler.naver_map_crawler.Stealth', None), \
        patch('app.crawler.naver_map_crawler.apply_stealth_sync', None):
        yield

# Fixture to simulate installed dependencies
@pytest.fixture
def mock_installed_packages():
    mock_ua_class = MagicMock()
    mock_ua_instance = MagicMock()
    mock_ua_instance.random = "Mocked/UserAgent 1.0"
    mock_ua_class.return_value = mock_ua_instance
    
    mock_stealth_class = MagicMock()
    mock_stealth_instance = MagicMock()
    mock_stealth_class.return_value = mock_stealth_instance
    
    mock_apply = MagicMock()
    
    with patch('app.crawler.naver_map_crawler.UserAgent', mock_ua_class), \
         patch('app.crawler.naver_map_crawler.Stealth', mock_stealth_class), \
         patch('app.crawler.naver_map_crawler.apply_stealth_sync', mock_apply):
        yield mock_ua_instance, mock_apply



def test_search_sync_integration():
    """_search_sync 내부에서 헬퍼 메서드들이 호출되는지 통합 검증"""
    crawler = NaverMapCrawler(headless=True)
    
    with patch('app.crawler.naver_map_crawler.sync_playwright') as mock_pw, \
         patch('app.crawler.naver_map_crawler.UserAgent') as mock_ua_class, \
         patch('app.crawler.naver_map_crawler.stealth_sync', create=True) as mock_stealth_sync:

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
        
        # 내부 데이터 추출 메서드만 모킹
        with patch.object(crawler, '_extract_apollo_state_sync', return_value=[]):
            crawler._search_sync("test_query")
            
            # 2. Context 생성 시 UA 전달 확인
            call_args = mock_browser.new_context.call_args
            assert call_args.kwargs['user_agent'] == "Test-UA"
            
            # 3. Stealth 로직 (Playwright) 호출 확인
            assert mock_stealth_sync.call_count == 1
            mock_stealth_sync.assert_called_with(mock_context)

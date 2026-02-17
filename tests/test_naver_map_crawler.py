import pytest
import sys
from unittest.mock import MagicMock, patch
from app.crawler.naver_map_crawler import NaverMapCrawler

# Fixture to simulate missing dependencies
@pytest.fixture
def mock_missing_packages():
    with patch.dict(sys.modules, {'fake_useragent': None, 'playwright_stealth': None}):
        yield

# Fixture to simulate installed dependencies
@pytest.fixture
def mock_installed_packages():
    mock_ua_module = MagicMock()
    mock_ua_class = MagicMock()
    mock_ua_instance = MagicMock()
    mock_ua_instance.random = "Mocked/UserAgent 1.0"
    mock_ua_class.return_value = mock_ua_instance
    mock_ua_module.UserAgent = mock_ua_class
    
    mock_stealth_module = MagicMock()
    
    with patch.dict(sys.modules, {
        'fake_useragent': mock_ua_module, 
        'playwright_stealth': mock_stealth_module
    }):
        yield mock_ua_instance, mock_stealth_module

def test_get_random_ua_installed(mock_installed_packages):
    """fake-useragent 설치 시 랜덤 UA 반환 검증"""
    crawler = NaverMapCrawler(headless=True)
    ua = crawler._get_random_ua()
    assert ua == "Mocked/UserAgent 1.0"

def test_get_random_ua_missing(mock_missing_packages):
    """fake-useragent 미설치 시 Fallback UA 반환 검증"""
    crawler = NaverMapCrawler(headless=True)
    ua = crawler._get_random_ua()
    assert "Mozilla/5.0" in ua
    assert "Mocked" not in ua

def test_apply_stealth_installed(mock_installed_packages):
    """playwright-stealth 설치 시 stealth() 호출 검증"""
    _, mock_stealth_module = mock_installed_packages
    crawler = NaverMapCrawler(headless=True)
    mock_page = MagicMock()
    
    crawler._apply_stealth(mock_page)
    
    mock_stealth_module.stealth.assert_called_once_with(mock_page)

def test_apply_stealth_missing(mock_missing_packages):
    """playwright-stealth 미설치 시 에러 없이 로그만 남기는지 검증"""
    crawler = NaverMapCrawler(headless=True)
    mock_page = MagicMock()
    
    # 예외가 발생하지 않아야 함
    crawler._apply_stealth(mock_page)

def test_search_sync_integration():
    """_search_sync 내부에서 헬퍼 메서드들이 호출되는지 통합 검증"""
    crawler = NaverMapCrawler(headless=True)
    
    with patch('app.crawler.naver_map_crawler.sync_playwright') as mock_pw:
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        
        mock_pw.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        
        # 내부 메서드 Mocking (실제 로직 실행 방지)
        with patch.object(crawler, '_get_random_ua', return_value="Test-UA") as mock_get_ua, \
             patch.object(crawler, '_apply_stealth') as mock_apply_stealth, \
             patch.object(crawler, '_extract_apollo_state_sync', return_value=[]):
            
            crawler._search_sync("test_query")
            
            # 1. UA 생성 호출 확인
            mock_get_ua.assert_called_once()
            
            # 2. Context 생성 시 UA 전달 확인
            call_args = mock_browser.new_context.call_args
            assert call_args.kwargs['user_agent'] == "Test-UA"
            
            # 3. Stealth 적용 호출 확인
            mock_apply_stealth.assert_called_once_with(mock_page)

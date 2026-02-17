import pytest
import sys
from unittest.mock import MagicMock, patch
from app.crawler.naver_map_crawler import NaverMapCrawler

# Fixture to simulate missing dependencies
@pytest.fixture
def mock_missing_packages():
    with patch('app.crawler.naver_map_crawler.UserAgent', None), \
         patch('app.crawler.naver_map_crawler.Stealth', None):
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

def test_get_random_ua_installed(mock_installed_packages):
    """fake-useragent 설치 시 랜덤 UA 반환 검증"""
    _ = mock_installed_packages
    crawler = NaverMapCrawler(headless=True)
    ua = crawler._get_random_ua()
    assert ua == "Mocked/UserAgent 1.0"

def test_get_random_ua_generic_exception(mock_installed_packages):
    """fake-useragent 사용 중 일반 예외(Exception) 발생 시 Fallback UA 반환 검증"""
    mock_ua_instance, _ = mock_installed_packages
    # random 접근 시 예외 발생 시뮬레이션
    type(mock_ua_instance).random = property(lambda _self: (_ for _ in ()).throw(Exception("Random Error")))
    
    crawler = NaverMapCrawler(headless=True)
    ua = crawler._get_random_ua()
    assert "Mozilla/5.0" in ua
    assert "Mocked" not in ua

def test_get_random_ua_missing(mock_missing_packages):
    """fake-useragent 미설치 시 Fallback UA 반환 검증"""
    _ = mock_missing_packages
    crawler = NaverMapCrawler(headless=True)
    ua = crawler._get_random_ua()
    assert "Mozilla/5.0" in ua
    assert "Mocked" not in ua

def test_apply_stealth_installed(mock_installed_packages):
    """playwright-stealth 설치 시 stealth() 호출 검증"""
    _, mock_apply = mock_installed_packages
    crawler = NaverMapCrawler(headless=True)
    mock_page = MagicMock()
    
    crawler._apply_stealth(mock_page)
    
    mock_apply.assert_called_once_with(mock_page)

def test_apply_stealth_missing(mock_missing_packages):
    """playwright-stealth 미설치 시 에러 없이 로그만 남기는지 검증"""
    _ = mock_missing_packages
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

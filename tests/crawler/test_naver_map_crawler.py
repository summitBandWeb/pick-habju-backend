# tests/crawler/test_naver_map_crawler.py
"""
NaverMapCrawler 단위 테스트

테스트 대상:
- _merge_results: 중복 제거하며 결과 병합
- Browser Launch Fallback: 크롬 채널 실패 시 번들 크로미움 재시도 확인

실행: pytest tests/crawler/test_naver_map_crawler.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
from app.crawler.naver_map_crawler import NaverMapCrawler


class TestMergeResults:
    """_merge_results 메서드 테스트"""
    
    @pytest.fixture
    def crawler(self):
        return NaverMapCrawler(headless=True)
    
    # ============== TC: 기본 병합 ==============
    def test_basic_merge(self, crawler):
        """새로운 아이템들이 target에 추가됨"""
        target = {}
        source = [
            {"id": "1", "name": "Room A"},
            {"id": "2", "name": "Room B"}
        ]
        
        crawler._merge_results(target, source)
        
        assert len(target) == 2
        assert target["1"]["name"] == "Room A"
        assert target["2"]["name"] == "Room B"
    
    # ============== TC: 중복 제거 ==============
    def test_deduplication(self, crawler):
        """이미 존재하는 ID는 추가되지 않음"""
        target = {"1": {"id": "1", "name": "Existing Room"}}
        source = [
            {"id": "1", "name": "Duplicate Room"},  # 중복
            {"id": "2", "name": "New Room"}
        ]
        
        crawler._merge_results(target, source)
        
        assert len(target) == 2
        assert target["1"]["name"] == "Existing Room"  # 기존 값 유지
        assert target["2"]["name"] == "New Room"
    
    # ============== TC: 빈 source ==============
    def test_empty_source(self, crawler):
        """source가 비어있으면 target 변경 없음"""
        target = {"1": {"id": "1", "name": "Room A"}}
        source = []
        
        crawler._merge_results(target, source)
        
        assert len(target) == 1
    
    # ============== TC: 비정상 아이템 스킵 ==============
    def test_skip_non_dict_items(self, crawler):
        """dict가 아닌 아이템은 스킵"""
        target = {}
        source = [
            {"id": "1", "name": "Room A"},
            "invalid_string",  # 비정상
            123,               # 비정상
            {"id": "2", "name": "Room B"}
        ]
        
        crawler._merge_results(target, source)
        
        assert len(target) == 2
        assert "1" in target
        assert "2" in target
    
    # ============== TC: 연속 병합 ==============
    def test_multiple_merges(self, crawler):
        """여러 번 병합해도 중복 없이 누적"""
        target = {}
        
        crawler._merge_results(target, [{"id": "1", "name": "Room A"}])
        crawler._merge_results(target, [{"id": "2", "name": "Room B"}])
        crawler._merge_results(target, [{"id": "1", "name": "Duplicate A"}])  # 중복
        
        assert len(target) == 2
        assert target["1"]["name"] == "Room A"  # 첫 번째 값 유지


class TestCrawlerRobustness:
    """크롤러 안정성 및 Fallback 테스트"""

    @pytest.fixture
    def crawler(self):
        return NaverMapCrawler(headless=True)

    @patch("app.crawler.naver_map_crawler.sync_playwright")
    def test_browser_launch_fallback(self, mock_playwright, crawler):
        """Chrome 채널 launch 실패 시 번들 chromium으로 재시도하는지 검증"""
        # Mock Playwright & Browser objects
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        # Context manager setup
        mock_playwright.return_value.__enter__.return_value = mock_p
        
        # Browser/Context/Page chain setup
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        # Side effect: First call raises Exception, Second call returns mock_browser
        mock_p.chromium.launch.side_effect = [Exception("Chrome channel not found"), mock_browser]

        # Act
        crawler._search_sync("test_query")

        # Assert
        # launch가 총 2번 호출되었는지 확인
        assert mock_p.chromium.launch.call_count == 2
        
        # 호출 인자 검증
        calls = mock_p.chromium.launch.call_args_list
        
        # 첫 번째 호출: channel='chrome' 포함 -> 실패 유도
        first_call_kwargs = calls[0].kwargs
        assert first_call_kwargs.get("channel") == "chrome"
        
        # 두 번째 호출: channel 없음 -> 성공 (Fallback)
        second_call_kwargs = calls[1].kwargs
        assert "channel" not in second_call_kwargs

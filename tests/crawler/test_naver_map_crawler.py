# tests/crawler/test_naver_map_crawler.py
"""
NaverMapCrawler unit tests.

Run:
    pytest tests/crawler/test_naver_map_crawler.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

from app.crawler.naver_map_crawler import NaverMapCrawler


class TestMergeResults:
    @pytest.fixture
    def crawler(self):
        return NaverMapCrawler(headless=True)

    def test_basic_merge(self, crawler):
        target = {}
        source = [
            {"id": "1", "name": "Room A"},
            {"id": "2", "name": "Room B"},
        ]

        crawler._merge_results(target, source)

        assert len(target) == 2
        assert target["1"]["name"] == "Room A"
        assert target["2"]["name"] == "Room B"

    def test_deduplication(self, crawler):
        target = {"1": {"id": "1", "name": "Existing Room"}}
        source = [
            {"id": "1", "name": "Duplicate Room"},
            {"id": "2", "name": "New Room"},
        ]

        crawler._merge_results(target, source)

        assert len(target) == 2
        assert target["1"]["name"] == "Existing Room"
        assert target["2"]["name"] == "New Room"

    def test_empty_source(self, crawler):
        target = {"1": {"id": "1", "name": "Room A"}}
        source = []

        crawler._merge_results(target, source)

        assert len(target) == 1

    def test_skip_non_dict_items(self, crawler):
        target = {}
        source = [
            {"id": "1", "name": "Room A"},
            "invalid_string",
            123,
            {"id": "2", "name": "Room B"},
        ]

        crawler._merge_results(target, source)

        assert len(target) == 2
        assert "1" in target
        assert "2" in target

    def test_skip_dict_without_id(self, crawler):
        target = {}
        source = [
            {"id": "1", "name": "Room A"},
            {"name": "Missing ID"},
            {},
            {"id": None, "name": "Invalid ID"},
            {"id": "2", "name": "Room B"},
        ]

        crawler._merge_results(target, source)

        assert len(target) == 2
        assert "1" in target
        assert "2" in target

    def test_multiple_merges(self, crawler):
        target = {}

        crawler._merge_results(target, [{"id": "1", "name": "Room A"}])
        crawler._merge_results(target, [{"id": "2", "name": "Room B"}])
        crawler._merge_results(target, [{"id": "1", "name": "Duplicate A"}])

        assert len(target) == 2
        assert target["1"]["name"] == "Room A"


class TestCrawlerRobustness:
    @pytest.fixture
    def crawler(self):
        return NaverMapCrawler(headless=True)

    @patch("app.crawler.naver_map_crawler.sync_playwright")
    def test_browser_launch_fallback(self, mock_playwright, crawler):
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_p.chromium.launch.side_effect = [Exception("Chrome channel not found"), mock_browser]

        crawler._search_sync("test_query")

        assert mock_p.chromium.launch.call_count == 2
        calls = mock_p.chromium.launch.call_args_list
        assert calls[0].kwargs.get("channel") == "chrome"
        assert "channel" not in calls[1].kwargs

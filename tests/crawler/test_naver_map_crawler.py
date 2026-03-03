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
            {"id": "1", "bookingBusinessId": "1", "name": "Room A"},
            {"id": "2", "bookingBusinessId": "2", "name": "Room B"},
        ]

        crawler._merge_results(target, source)

        assert len(target) == 2
        assert target["1"]["name"] == "Room A"
        assert target["2"]["name"] == "Room B"

    def test_deduplication(self, crawler):
        target = {"1": {"id": "1", "name": "Existing Room"}}
        source = [
            {"id": "1", "bookingBusinessId": "1", "name": "Duplicate Room"},
            {"id": "2", "bookingBusinessId": "2", "name": "New Room"},
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
            {"id": "1", "bookingBusinessId": "1", "name": "Room A"},
            "invalid_string",
            123,
            {"id": "2", "bookingBusinessId": "2", "name": "Room B"},
        ]

        crawler._merge_results(target, source)

        assert len(target) == 2
        assert "1" in target
        assert "2" in target

    def test_skip_dict_without_id(self, crawler):
        target = {}
        source = [
            {"id": "1", "bookingBusinessId": "1", "name": "Room A"},
            {"name": "Missing ID"},
            {},
            {"id": None, "name": "Invalid ID"},
            {"id": "2", "bookingBusinessId": "2", "name": "Room B"},
        ]

        crawler._merge_results(target, source)

        assert len(target) == 2
        assert "1" in target
        assert "2" in target

    def test_multiple_merges(self, crawler):
        target = {}

        crawler._merge_results(target, [{"id": "1", "bookingBusinessId": "1", "name": "Room A"}])
        crawler._merge_results(target, [{"id": "2", "bookingBusinessId": "2", "name": "Room B"}])
        crawler._merge_results(target, [{"id": "1", "bookingBusinessId": "1", "name": "Duplicate A"}])

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

    def test_goto_search_page_retries_on_429_then_succeeds(self, crawler):
        page = MagicMock()
        crawler.RATE_LIMIT_RETRIES = 2
        crawler.RATE_LIMIT_BACKOFF_SEC = 0.0
        crawler.PAGE_WAIT_JITTER_MS = 0

        rate_limited_resp = MagicMock()
        rate_limited_resp.status = 429
        ok_resp = MagicMock()
        ok_resp.status = 200
        page.goto.side_effect = [rate_limited_resp, ok_resp]

        ok = crawler._goto_search_page_with_retry(page, "https://example.com")

        assert ok is True
        assert page.goto.call_count == 2
        page.wait_for_load_state.assert_called_once_with("networkidle")
        page.wait_for_timeout.assert_called_once()

    def test_goto_search_page_retries_exhausted_on_429(self, crawler):
        page = MagicMock()
        crawler.RATE_LIMIT_RETRIES = 2
        crawler.RATE_LIMIT_BACKOFF_SEC = 0.0
        crawler.PAGE_WAIT_JITTER_MS = 0

        rate_limited_resp = MagicMock()
        rate_limited_resp.status = 429
        page.goto.side_effect = [rate_limited_resp, rate_limited_resp, rate_limited_resp]

        ok = crawler._goto_search_page_with_retry(page, "https://example.com")

        assert ok is False
        assert page.goto.call_count == 3
        page.wait_for_load_state.assert_not_called()


class TestPhoneRevealHelpers:
    @pytest.fixture
    def crawler(self):
        return NaverMapCrawler(headless=True)

    def test_extract_phone_candidate_from_text(self, crawler):
        text = "문의는 전화번호 보기 클릭 후 0507-1461-8067로 연락해주세요."
        assert crawler._extract_phone_candidate(text) == "0507-1461-8067"

    def test_decode_phone_payload_from_base64_json(self, crawler):
        payload = "eyJudW1iZXIiOiIwMTAtMzAzMi02MDMzIn0="
        assert crawler._decode_phone_payload(payload) == "010-3032-6033"


class TestRepresentativeKeywordHelpers:
    @pytest.fixture
    def crawler(self):
        return NaverMapCrawler(headless=True)

    def test_extract_representative_keywords_from_text(self, crawler):
        text = """
        소개
        안내 문구

        대표 키워드
        합주실   음악연습실   악기연습실   밴드합주실
        음악

        이용안내
        """
        assert crawler._extract_representative_keywords_from_text(text) == [
            "합주실",
            "음악연습실",
            "악기연습실",
            "밴드합주실",
            "음악",
        ]

    def test_extract_representative_keywords_from_text_without_marker(self, crawler):
        text = "소개\n합주 가능\n문의 010-0000-0000"
        assert crawler._extract_representative_keywords_from_text(text) == []

    def test_normalize_representative_keywords_deduplicates(self, crawler):
        assert crawler._normalize_representative_keywords(
            [" 합주실 ", "음악연습실", "합주실", "음악연습실", "  "]
        ) == ["합주실", "음악연습실"]

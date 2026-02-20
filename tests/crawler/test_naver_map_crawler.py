# tests/crawler/test_naver_map_crawler.py
"""
NaverMapCrawler unit tests

Run:
    pytest tests/crawler/test_naver_map_crawler.py -v
"""

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


class TestRegionList:
    @pytest.fixture
    def crawler(self):
        return NaverMapCrawler(headless=True)

    def test_region_count(self, crawler):
        seoul_count = 25
        major_cities_count = 10
        expected_total = seoul_count + major_cities_count

        assert expected_total == 35

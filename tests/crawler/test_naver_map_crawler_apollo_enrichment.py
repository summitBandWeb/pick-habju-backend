from unittest.mock import MagicMock

from app.crawler.naver_map_crawler import NaverMapCrawler


def test_extract_apollo_state_script_includes_enrichment_prefixes():
    crawler = NaverMapCrawler(headless=True)
    page = MagicMock()
    page.evaluate.return_value = []

    crawler._extract_apollo_state_sync(page)

    script = page.evaluate.call_args.args[0]
    assert "PlaceSummary:" in script
    assert "PlaceDetail:" in script
    assert "BookingBusiness:" in script

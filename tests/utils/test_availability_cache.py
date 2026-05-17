import time
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta
from app.utils.availability_cache import AvailabilityCache

FUTURE_DATE = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
BIZ_ITEM_ID = "r1"
START_HOUR = "14:00"
END_HOUR = "16:00"
CACHED_DATA = {"available": True}


@pytest.fixture
def cache():
    return AvailabilityCache(ttl_seconds=1)


def test_cache_hit_within_ttl(cache):
    """TTL 이내 동일 키 재조회 시 캐시 히트를 반환한다."""
    cache.set(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, CACHED_DATA)
    result = cache.get(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID)
    assert result == CACHED_DATA

def test_cache_miss_after_ttl_expires(cache):
    cache.set(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, CACHED_DATA)
    with patch("app.utils.availability_cache.time") as mock_time:
        mock_time.time.return_value = time.time() + 2  # TTL(1s) 초과
        result = cache.get(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID)
    assert result is None


def test_cache_different_keys_are_isolated(cache):
    """날짜·시간·방 ID가 다른 키는 서로 간섭하지 않는다."""
    other_date = (datetime.now() + timedelta(days=31)).strftime("%Y-%m-%d")
    cache.set(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, CACHED_DATA)
    assert cache.get(other_date, START_HOUR, END_HOUR, BIZ_ITEM_ID) is None


def test_cache_returns_deep_copy(cache):
    """캐시가 반환한 객체를 수정해도 캐시 원본에 영향을 주지 않는다."""
    cache.set(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, CACHED_DATA)
    result = cache.get(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID)
    result["available"] = False
    assert cache.get(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID) == CACHED_DATA


def test_cache_clear_removes_all_entries(cache):
    """clear() 호출 시 모든 캐시 항목이 제거된다."""
    cache.set(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, CACHED_DATA)
    cache.clear()
    assert cache.get(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID) is None

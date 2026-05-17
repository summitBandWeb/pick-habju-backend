import asyncio
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
    """TTL 만료 후 동일 키 조회 시 캐시 미스(None)를 반환한다."""
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


# ---------------------------------------------------------------------------
# is_pending
# ---------------------------------------------------------------------------

def test_is_pending_returns_false_when_no_cache_and_no_inflight(cache):
    """캐시도 없고 진행 중인 요청도 없으면 False를 반환한다."""
    assert cache.is_pending(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID) is False


def test_is_pending_returns_true_when_cache_alive(cache):
    """유효한 캐시가 있으면 True를 반환한다."""
    cache.set(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, CACHED_DATA)
    assert cache.is_pending(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID) is True


def test_is_pending_returns_true_when_inflight(cache):
    """_inflight에 진행 중인 Future가 있으면 True를 반환한다."""
    key = cache._get_key(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID)
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        cache._inflight[key] = future
        assert cache.is_pending(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID) is True
    finally:
        future.cancel()
        loop.close()


# ---------------------------------------------------------------------------
# get_or_compute
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_or_compute_cache_miss_calls_factory_once_and_caches(cache):
    """캐시 미스 시 factory가 정확히 1회 호출되고 결과가 캐싱된다."""
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        return CACHED_DATA

    result = await cache.get_or_compute(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, factory)
    assert result == CACHED_DATA
    assert call_count == 1
    assert cache.get(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID) == CACHED_DATA


@pytest.mark.asyncio
async def test_get_or_compute_cache_hit_skips_factory(cache):
    """캐시 히트 시 factory가 호출되지 않는다."""
    cache.set(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, CACHED_DATA)
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        return {"should": "not reach here"}

    result = await cache.get_or_compute(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, factory)
    assert result == CACHED_DATA
    assert call_count == 0


@pytest.mark.asyncio
async def test_get_or_compute_stampede_factory_called_once(cache):
    """동시 요청이 몰려도 factory는 1회만 실행되고 모든 호출이 같은 결과를 받는다."""
    call_count = 0

    async def slow_factory():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0)  # 이벤트 루프에 제어권을 넘겨 다른 코루틴이 실행되도록 함
        return CACHED_DATA

    results = await asyncio.gather(
        cache.get_or_compute(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, slow_factory),
        cache.get_or_compute(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, slow_factory),
        cache.get_or_compute(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, slow_factory),
    )

    assert call_count == 1
    assert all(r == CACHED_DATA for r in results)


@pytest.mark.asyncio
async def test_get_or_compute_factory_exception_propagates_and_cleans_inflight(cache):
    """factory 예외 발생 시 예외가 호출부로 전파되고 _inflight에서 정리된다."""
    async def failing_factory():
        raise ValueError("computation failed")

    with pytest.raises(ValueError, match="computation failed"):
        await cache.get_or_compute(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID, failing_factory)

    key = cache._get_key(FUTURE_DATE, START_HOUR, END_HOUR, BIZ_ITEM_ID)
    assert key not in cache._inflight

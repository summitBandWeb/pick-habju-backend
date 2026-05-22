# tests/test_naver_checker.py
import pytest
import os
import importlib

from datetime import datetime, timedelta
from app.crawler.naver_checker import NaverCrawler
from app.models.dto import RoomDetail
from app.utils.room_loader import get_rooms_by_criteria

RUN_EXTERNAL_TESTS = os.getenv("RUN_EXTERNAL_TESTS") == "1"


def test_semaphore_default_values(monkeypatch):
    """NAVER_CRAWLER_SEMAPHORE, NAVER_PREFETCH_SEMAPHORE 미설정 시 기본값이 60인지 확인."""
    monkeypatch.delenv("NAVER_CRAWLER_SEMAPHORE", raising=False)
    monkeypatch.delenv("NAVER_PREFETCH_SEMAPHORE", raising=False)

    import app.crawler.naver_checker as m
    importlib.reload(m)

    assert m.NaverCrawler._semaphore._value == 60
    assert m.NaverCrawler._prefetch_semaphore._value == 60


def test_semaphore_invalid_env(monkeypatch):
    """환경변수에 정수로 변환 불가한 값이 있을 때 기본값 60으로 폴백하는지 확인."""
    monkeypatch.setenv("NAVER_CRAWLER_SEMAPHORE", "abc")
    monkeypatch.setenv("NAVER_PREFETCH_SEMAPHORE", "xyz")

    import app.crawler.naver_checker as m
    importlib.reload(m)

    assert m.NaverCrawler._semaphore._value == 60
    assert m.NaverCrawler._prefetch_semaphore._value == 60


@pytest.mark.skipif(
    not RUN_EXTERNAL_TESTS,
    reason="External crawler test disabled. Set RUN_EXTERNAL_TESTS=1 to run.",
)
@pytest.mark.asyncio
async def test_get_naver_availability():
    date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    hour_slots = ["15:00", "16:00", "17:00"]
    naver_rooms = []
    for item in await get_rooms_by_criteria(capacity=1):
        if item.branch != "그루브 사당점" and item.branch != "드림합주실 사당점":
            room = RoomDetail(
                name=item.name,
                branch=item.branch,
                business_id=item.business_id,
                biz_item_id=item.biz_item_id,
                imageUrls=item.imageUrls,
                maxCapacity=item.maxCapacity,
                recommend_capacity_range=item.recommendCapacityRange,
                pricePerHour=item.pricePerHour,
                canReserveOneHour=item.canReserveOneHour,
                requires_contact_on_sameday=item.requiresContactOnSameDay
            )
            naver_rooms.append(room)

    crawler = NaverCrawler()
    result = await crawler.check_availability(date, hour_slots, naver_rooms)

    success_results = [r for r in result if not isinstance(r, Exception)]
    error_results = [r for r in result if isinstance(r, Exception)]

    if error_results:
        print(f"\n⚠️ {len(error_results)}개 룸 조회 실패:")
        for err in error_results:
            print(f"  - {err}")

    print(f"\n✅ {len(success_results)}개 룸 조회 성공")

    assert isinstance(result, list)
    assert len(success_results) > 0, "모든 룸 조회가 실패했습니다. 네트워크 또는 API 문제일 수 있습니다."
    assert all(hasattr(r, "available_slots") for r in success_results)

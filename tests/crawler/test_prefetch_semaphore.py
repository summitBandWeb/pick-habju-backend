"""
크롤러 프리페치 세마포어 분리 검증 (#278)

세 크롤러(Naver, Dream, Groove) 모두:
- prefetch=False → _semaphore 사용
- prefetch=True  → _prefetch_semaphore 사용
- _prefetch_semaphore 포화 상태에서도 prefetch=False 요청은 블로킹 없이 진행
"""
import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.crawler.naver_checker import NaverCrawler
from app.crawler.dream_checker import DreamCrawler
from app.crawler.groove_checker import GrooveCrawler
from app.models.dto import RoomDetail


FUTURE_DATE = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
HOUR_SLOTS = ["15:00"]


# ---------------------------------------------------------------------------
# 공용 픽스처 / 헬퍼
# ---------------------------------------------------------------------------

class _TrackedSemaphore:
    """어떤 세마포어가 실제로 acquire됐는지 추적하는 가짜 세마포어."""
    def __init__(self):
        self.acquired = False

    async def __aenter__(self):
        self.acquired = True
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def naver_room():
    return RoomDetail(
        name="테스트룸", branch="테스트 지점", business_id="123456", biz_item_id="999",
        imageUrls=[], maxCapacity=6, recommend_capacity_range=[2, 4],
        pricePerHour=15000, canReserveOneHour=True, requiresContactOnSameDay=False,
    )


@pytest.fixture
def dream_room():
    return RoomDetail(
        name="드림 1룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="1",
        imageUrls=[], maxCapacity=6, recommend_capacity_range=[2, 4],
        pricePerHour=15000, canReserveOneHour=True, requiresContactOnSameDay=False,
    )


@pytest.fixture
def groove_room():
    return RoomDetail(
        name="A룸", branch="그루브 사당점", business_id="groove_sadang", biz_item_id="13",
        imageUrls=[], maxCapacity=6, recommend_capacity_range=[2, 4],
        pricePerHour=15000, canReserveOneHour=True, requiresContactOnSameDay=False,
    )


def _naver_mock_response():
    resp = MagicMock()
    resp.json.return_value = {"data": {"schedule": {"bizItemSchedule": {"hourly": []}}}}
    return resp


def _dream_mock_response():
    resp = MagicMock()
    resp.json.return_value = {"items": ""}
    return resp


# ---------------------------------------------------------------------------
# NaverCrawler
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_naver_normal_uses_semaphore(naver_room):
    """prefetch=False 시 NaverCrawler가 _semaphore를 사용한다."""
    normal_sem = _TrackedSemaphore()
    prefetch_sem = _TrackedSemaphore()

    with patch.object(NaverCrawler, "_semaphore", normal_sem), \
         patch.object(NaverCrawler, "_prefetch_semaphore", prefetch_sem), \
         patch("app.crawler.naver_checker.load_client", new_callable=AsyncMock, return_value=_naver_mock_response()):
        await NaverCrawler().check_availability(FUTURE_DATE, HOUR_SLOTS, [naver_room], prefetch=False)

    assert normal_sem.acquired is True
    assert prefetch_sem.acquired is False


@pytest.mark.asyncio
async def test_naver_prefetch_uses_prefetch_semaphore(naver_room):
    """prefetch=True 시 NaverCrawler가 _prefetch_semaphore를 사용한다."""
    normal_sem = _TrackedSemaphore()
    prefetch_sem = _TrackedSemaphore()

    with patch.object(NaverCrawler, "_semaphore", normal_sem), \
         patch.object(NaverCrawler, "_prefetch_semaphore", prefetch_sem), \
         patch("app.crawler.naver_checker.load_client", new_callable=AsyncMock, return_value=_naver_mock_response()):
        await NaverCrawler().check_availability(FUTURE_DATE, HOUR_SLOTS, [naver_room], prefetch=True)

    assert prefetch_sem.acquired is True
    assert normal_sem.acquired is False


@pytest.mark.asyncio
async def test_naver_normal_not_blocked_by_full_prefetch_semaphore(naver_room):
    """_prefetch_semaphore가 포화 상태(슬롯=0)여도 prefetch=False 요청은 블로킹 없이 완료된다."""
    with patch.object(NaverCrawler, "_prefetch_semaphore", asyncio.Semaphore(0)), \
         patch("app.crawler.naver_checker.load_client", new_callable=AsyncMock, return_value=_naver_mock_response()):
        result = await asyncio.wait_for(
            NaverCrawler().check_availability(FUTURE_DATE, HOUR_SLOTS, [naver_room], prefetch=False),
            timeout=1.0,
        )
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# DreamCrawler
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dream_normal_uses_semaphore(dream_room):
    """prefetch=False 시 DreamCrawler가 _semaphore를 사용한다."""
    normal_sem = _TrackedSemaphore()
    prefetch_sem = _TrackedSemaphore()

    with patch.object(DreamCrawler, "_semaphore", normal_sem), \
         patch.object(DreamCrawler, "_prefetch_semaphore", prefetch_sem), \
         patch("app.crawler.dream_checker.load_client", new_callable=AsyncMock, return_value=_dream_mock_response()):
        await DreamCrawler().check_availability(FUTURE_DATE, HOUR_SLOTS, [dream_room], prefetch=False)

    assert normal_sem.acquired is True
    assert prefetch_sem.acquired is False


@pytest.mark.asyncio
async def test_dream_prefetch_uses_prefetch_semaphore(dream_room):
    """prefetch=True 시 DreamCrawler가 _prefetch_semaphore를 사용한다."""
    normal_sem = _TrackedSemaphore()
    prefetch_sem = _TrackedSemaphore()

    with patch.object(DreamCrawler, "_semaphore", normal_sem), \
         patch.object(DreamCrawler, "_prefetch_semaphore", prefetch_sem), \
         patch("app.crawler.dream_checker.load_client", new_callable=AsyncMock, return_value=_dream_mock_response()):
        await DreamCrawler().check_availability(FUTURE_DATE, HOUR_SLOTS, [dream_room], prefetch=True)

    assert prefetch_sem.acquired is True
    assert normal_sem.acquired is False


@pytest.mark.asyncio
async def test_dream_normal_not_blocked_by_full_prefetch_semaphore(dream_room):
    """_prefetch_semaphore가 포화 상태(슬롯=0)여도 prefetch=False 요청은 블로킹 없이 완료된다."""
    with patch.object(DreamCrawler, "_prefetch_semaphore", asyncio.Semaphore(0)), \
         patch("app.crawler.dream_checker.load_client", new_callable=AsyncMock, return_value=_dream_mock_response()):
        result = await asyncio.wait_for(
            DreamCrawler().check_availability(FUTURE_DATE, HOUR_SLOTS, [dream_room], prefetch=False),
            timeout=1.0,
        )
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# GrooveCrawler
# ---------------------------------------------------------------------------

@pytest.fixture
def groove_mock_html(groove_room):
    biz_item_id = groove_room.biz_item_id
    return f'<div id="reserve_time_{biz_item_id}_15" class="reserve_time_off"></div>'


@pytest.mark.asyncio
async def test_groove_normal_uses_semaphore(groove_room, groove_mock_html):
    """prefetch=False 시 GrooveCrawler가 _semaphore를 사용한다."""
    normal_sem = _TrackedSemaphore()
    prefetch_sem = _TrackedSemaphore()

    with patch.object(GrooveCrawler, "_semaphore", normal_sem), \
         patch.object(GrooveCrawler, "_prefetch_semaphore", prefetch_sem), \
         patch.object(GrooveCrawler, "_login_and_fetch_html", new_callable=AsyncMock, return_value=groove_mock_html):
        await GrooveCrawler().check_availability(FUTURE_DATE, HOUR_SLOTS, [groove_room], prefetch=False)

    assert normal_sem.acquired is True
    assert prefetch_sem.acquired is False


@pytest.mark.asyncio
async def test_groove_prefetch_uses_prefetch_semaphore(groove_room, groove_mock_html):
    """prefetch=True 시 GrooveCrawler가 _prefetch_semaphore를 사용한다."""
    normal_sem = _TrackedSemaphore()
    prefetch_sem = _TrackedSemaphore()

    with patch.object(GrooveCrawler, "_semaphore", normal_sem), \
         patch.object(GrooveCrawler, "_prefetch_semaphore", prefetch_sem), \
         patch.object(GrooveCrawler, "_login_and_fetch_html", new_callable=AsyncMock, return_value=groove_mock_html):
        await GrooveCrawler().check_availability(FUTURE_DATE, HOUR_SLOTS, [groove_room], prefetch=True)

    assert prefetch_sem.acquired is True
    assert normal_sem.acquired is False


@pytest.mark.asyncio
async def test_groove_normal_not_blocked_by_full_prefetch_semaphore(groove_room, groove_mock_html):
    """_prefetch_semaphore가 포화 상태(슬롯=0)여도 prefetch=False 요청은 블로킹 없이 완료된다."""
    with patch.object(GrooveCrawler, "_prefetch_semaphore", asyncio.Semaphore(0)), \
         patch.object(GrooveCrawler, "_login_and_fetch_html", new_callable=AsyncMock, return_value=groove_mock_html):
        result = await asyncio.wait_for(
            GrooveCrawler().check_availability(FUTURE_DATE, HOUR_SLOTS, [groove_room], prefetch=False),
            timeout=1.0,
        )
    assert isinstance(result, list)

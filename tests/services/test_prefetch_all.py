"""
AvailabilityService.prefetch_all 단위 테스트 (#279)

커버리지:
- is_pending() True인 룸 스킵
- _prefetch_in_flight 중복 실행 방지
- DB 조회 실패 시 조기 종료 (크롤러 호출 없음)
- 크롤링 성공 시 결과가 availability_cache에 저장됨
- 개별 룸 예외가 다른 룸의 캐시 저장을 막지 않음
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.availability_service import AvailabilityService
from app.models.dto import AvailabilityRequest, RoomAvailability, RoomDetail
from app.utils.availability_cache import availability_cache

FUTURE_DATE = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")


@pytest.fixture(autouse=True)
def clear_cache():
    """각 테스트 전후로 캐시 및 클래스 레벨 in-flight set을 초기화하여 테스트 간 오염을 방지한다."""
    availability_cache.clear()
    AvailabilityService._prefetch_in_flight.clear()
    yield
    availability_cache.clear()
    AvailabilityService._prefetch_in_flight.clear()


def _make_request(**kwargs) -> AvailabilityRequest:
    """기본값이 채워진 AvailabilityRequest 팩토리."""
    defaults = dict(
        date=FUTURE_DATE, capacity=2, start_hour="14:00", end_hour="16:00",
        swLat=37.0, swLng=126.0, neLat=38.0, neLng=127.0,
    )
    defaults.update(kwargs)
    return AvailabilityRequest(**defaults)


def _make_room(biz_item_id: str = "r1", business_id: str = "b1") -> RoomDetail:
    """테스트용 RoomDetail 팩토리."""
    return RoomDetail(
        name="TestRoom", branch="Branch", business_id=business_id, biz_item_id=biz_item_id,
        pricePerHour=10000, max_capacity=10, can_reserve_one_hour=True,
        requiresContactOnSameDay=False, recommend_capacity_range=[2, 4],
    )


def _make_avail(room: RoomDetail) -> RoomAvailability:
    """완전 예약 가능 RoomAvailability 팩토리."""
    return RoomAvailability(
        room_detail=room, available=True,
        available_slots={"14:00": True, "15:00": True},
    )


@pytest.fixture
def mock_crawler():
    """AsyncMock check_availability를 가진 가짜 크롤러."""
    crawler = MagicMock()
    crawler.check_availability = AsyncMock()
    return crawler


@pytest.fixture
def service(mock_crawler):
    """naver 크롤러만 주입된 AvailabilityService."""
    return AvailabilityService({"naver": mock_crawler})


@pytest.mark.asyncio
async def test_prefetch_all_skips_pending_rooms(service, mock_crawler):
    """is_pending()이 True인 룸은 target_rooms에서 제외되어 크롤러가 호출되지 않는다."""
    room = _make_room("r1")
    availability_cache.set(FUTURE_DATE, "14:00", "16:00", "r1", _make_avail(room))

    req = _make_request()
    with patch("app.services.availability_service.get_rooms_by_criteria", return_value=[room]):
        await service.prefetch_all(req)

    mock_crawler.check_availability.assert_not_called()


@pytest.mark.asyncio
async def test_prefetch_all_prevents_duplicate_execution(service, mock_crawler):
    """_prefetch_in_flight에 동일 키가 있으면 두 번째 호출은 DB 조회 없이 즉시 반환된다."""
    req = _make_request()
    lock_key = (req.date, req.start_hour, req.end_hour)
    AvailabilityService._prefetch_in_flight.add(lock_key)

    with patch("app.services.availability_service.get_rooms_by_criteria") as mock_db:
        await service.prefetch_all(req)

    mock_db.assert_not_called()
    mock_crawler.check_availability.assert_not_called()


@pytest.mark.asyncio
async def test_prefetch_all_early_return_on_db_failure(service, mock_crawler):
    """DB 조회 실패 시 크롤러를 호출하지 않고 조기 종료한다."""
    req = _make_request()
    with patch("app.services.availability_service.get_rooms_by_criteria", side_effect=Exception("DB 오류")):
        await service.prefetch_all(req)

    mock_crawler.check_availability.assert_not_called()


@pytest.mark.asyncio
async def test_prefetch_all_stores_results_in_cache(service, mock_crawler):
    """크롤링 성공 결과가 availability_cache에 저장된다."""
    room = _make_room("r1")
    avail = _make_avail(room)
    mock_crawler.check_availability.return_value = [avail]

    req = _make_request()
    with patch("app.services.availability_service.get_rooms_by_criteria", return_value=[room]), \
         patch("app.services.availability_service.filter_rooms_by_type", return_value=[room]):
        await service.prefetch_all(req)

    cached = availability_cache.get(FUTURE_DATE, "14:00", "16:00", "r1")
    assert cached is not None
    assert cached.available is True


@pytest.mark.asyncio
async def test_prefetch_all_individual_failure_does_not_block_others(service, mock_crawler):
    """개별 룸 예외(Exception)가 다른 룸의 캐시 저장을 막지 않는다."""
    room_ok = _make_room("r1")
    room_fail = _make_room("r2")
    avail_ok = _make_avail(room_ok)

    mock_crawler.check_availability.return_value = [avail_ok, Exception("r2 크롤링 실패")]

    req = _make_request()
    with patch("app.services.availability_service.get_rooms_by_criteria", return_value=[room_ok, room_fail]), \
         patch("app.services.availability_service.filter_rooms_by_type", return_value=[room_ok, room_fail]):
        await service.prefetch_all(req)

    assert availability_cache.get(FUTURE_DATE, "14:00", "16:00", "r1") is not None
    assert availability_cache.get(FUTURE_DATE, "14:00", "16:00", "r2") is None


@pytest.mark.asyncio
async def test_prefetch_all_inflight_cleared_after_completion(service, mock_crawler):
    """prefetch_all 완료 후 _prefetch_in_flight에서 키가 제거된다."""
    room = _make_room("r1")
    mock_crawler.check_availability.return_value = [_make_avail(room)]

    req = _make_request()
    lock_key = (req.date, req.start_hour, req.end_hour)

    with patch("app.services.availability_service.get_rooms_by_criteria", return_value=[room]), \
         patch("app.services.availability_service.filter_rooms_by_type", return_value=[room]):
        await service.prefetch_all(req)

    assert lock_key not in AvailabilityService._prefetch_in_flight


@pytest.mark.asyncio
async def test_prefetch_all_inflight_cleared_on_db_failure(service, mock_crawler):
    """DB 실패로 조기 종료해도 _prefetch_in_flight에서 키가 제거된다."""
    req = _make_request()
    lock_key = (req.date, req.start_hour, req.end_hour)

    with patch("app.services.availability_service.get_rooms_by_criteria", side_effect=Exception("DB 오류")):
        await service.prefetch_all(req)

    assert lock_key not in AvailabilityService._prefetch_in_flight


@pytest.mark.asyncio
async def test_prefetch_all_overnight_merges_day1_and_day2(service, mock_crawler):
    """overnight(start > end) 요청 시 day1/day2 크롤러 결과가 병합되어 캐시에 저장된다."""
    room = _make_room("r1")
    day1_avail = RoomAvailability(
        room_detail=room, available=True,
        available_slots={"23:00": True},
        estimated_price=10000,
    )
    day2_avail = RoomAvailability(
        room_detail=room, available=True,
        available_slots={"00:00": True, "01:00": True},
        estimated_price=20000,
    )
    mock_crawler.check_availability.side_effect = [[day1_avail], [day2_avail]]

    req = _make_request(start_hour="23:00", end_hour="02:00")
    with patch("app.services.availability_service.get_rooms_by_criteria", return_value=[room]), \
         patch("app.services.availability_service.filter_rooms_by_type", return_value=[room]):
        await service.prefetch_all(req)

    assert mock_crawler.check_availability.call_count == 2

    cached = availability_cache.get(FUTURE_DATE, "23:00", "02:00", "r1")
    assert cached is not None
    assert cached.available_slots == {"23:00": True, "00:00": True, "01:00": True}
    assert cached.estimated_price == 30000  # day1(10000) + day2(20000) 누산

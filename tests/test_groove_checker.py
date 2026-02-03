import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.exception.crawler.groove_exception import GrooveLoginError, GrooveCredentialError
from app.models.dto import RoomDetail
from app.crawler.groove_checker import GrooveCrawler
from app.utils.room_loader import get_rooms_by_criteria

@pytest.fixture(scope="module")
def sample_groove_rooms():
    """테스트를 위한 그루브 연습실 RoomDetail 객체 샘플 목록을 제공합니다."""
    rooms = []
    for item in get_rooms_by_criteria(capacity=1):
        if item.branch == "그루브 사당점":
            # 테스트의 일관성과 명확성을 위해 biz_item_id를 '13'으로 고정합니다.
            item.biz_item_id = '13'
            room = RoomDetail(
                name=item.name,
                branch=item.branch,
                business_id=item.business_id,
                biz_item_id=item.biz_item_id,
                imageUrls=item.imageUrls,
                maxCapacity=item.maxCapacity,
                recommendCapacity=item.recommendCapacity,
                pricePerHour=item.pricePerHour,
                canReserveOneHour=item.canReserveOneHour,
                requiresCallOnSameDay=item.requiresCallOnSameDay
            )
            rooms.append(room)
    # 하나의 샘플만 사용해 테스트를 단순화합니다.
    return rooms[:1]


# --- 1. 예외 및 기본 오류 상황 테스트 ---
@pytest.mark.asyncio
async def test_groove_login_error_simulation(sample_groove_rooms):
    """GrooveLoginError 예외가 리스트로 반환되는지 테스트"""
    future_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    crawler = GrooveCrawler()

    # 클래스 내부의 private 메서드를 모킹합니다.
    with patch.object(GrooveCrawler, '_login_and_fetch_html', side_effect=GrooveLoginError):
        results = await crawler.check_availability(future_date, ["20:00"], sample_groove_rooms)

    # 예외가 리스트에 담겨 반환되는지 확인
    assert len(results) == len(sample_groove_rooms)
    assert isinstance(results[0], GrooveLoginError)
    assert results[0].error_code.value == "CRAWLER-003"  # ErrorCode.CRAWLER_AUTH_FAILED
    assert results[0].status_code == 500


@pytest.mark.asyncio
async def test_groove_credential_error_simulation(sample_groove_rooms):
    """GrooveCredentialError 예외가 리스트로 반환되는지 테스트"""
    future_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    crawler = GrooveCrawler()

    with patch.object(GrooveCrawler, '_login_and_fetch_html', side_effect=GrooveCredentialError):
        results = await crawler.check_availability(future_date, ["20:00"], sample_groove_rooms)

    # 예외가 리스트에 담겨 반환되는지 확인
    assert len(results) == len(sample_groove_rooms)
    assert isinstance(results[0], GrooveCredentialError)
    assert results[0].error_code.value == "CRAWLER-003"  # ErrorCode.CRAWLER_AUTH_FAILED
    assert results[0].status_code == 401

# --- 2. 경계값 분석 테스트 ---

@pytest.mark.asyncio
async def test_availability_within_84_days_boundary(sample_groove_rooms):
    """
    [경계값] 83일 후: 예약 가능/불가능 상태가 정상적으로 True/False로 반환되는지 테스트합니다.
    """
    # 사용된 biz_item_id를 fixture에서 가져옵니다.
    biz_item_id = sample_groove_rooms[0].biz_item_id
    crawler = GrooveCrawler()

    mock_html = f"""
    <div id="reserve_section_{biz_item_id}">
        <div id="reserve_time_{biz_item_id}_20" class="reserve_time_off"></div>
        <td class="ok"></td>
    </div>
    """

    # 경계값인 83일 후 날짜를 설정
    target_date = (datetime.now() + timedelta(days=83)).strftime("%Y-%m-%d")
    hour_slots = ["20:00", "21:00"]

    with patch.object(GrooveCrawler, '_login_and_fetch_html', return_value=mock_html):
        results = await crawler.check_availability(target_date, hour_slots, sample_groove_rooms)

    print(results)
    # 검증
    # check_hour_slot은 '#reserve_time_..._21.reserve_time_off'를 찾지 못하므로 False를 반환함
    result = results[0]
    assert result.available is False  # 한 슬롯이라도 불가능하면 전체는 False
    assert result.available_slots["20:00"] is True
    assert result.available_slots["21:00"] is False


@pytest.mark.asyncio
async def test_availability_at_and_after_84_days_boundary(sample_groove_rooms):
    """
    [경계값] 84일 후: 모든 상태가 'unknown'으로 반환되는지 테스트합니다. (네트워크 요청 없음)
    """
    target_date = (datetime.now() + timedelta(days=84)).strftime("%Y-%m-%d")
    hour_slots = ["20:00", "21:00"]
    crawler = GrooveCrawler()

    results = await crawler.check_availability(target_date, hour_slots, sample_groove_rooms)
    print(results)
    # 검증
    result = results[0]
    assert result.available == "unknown"
    assert result.available_slots["20:00"] == "unknown"
    assert result.available_slots["21:00"] == "unknown"

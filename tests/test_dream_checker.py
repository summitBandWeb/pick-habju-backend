"""
드림 연습실 크롤러 테스트 모듈

Rationale:
    기존 테스트는 get_rooms_by_criteria(DB 호출)와 실제 외부 HTTP 요청에
    의존하여 환경(네트워크, DB 상태)에 따라 불안정했음.
    하드코딩된 RoomDetail과 Mock HTTP 응답으로 교체하여
    CI/CD 환경에서도 항상 동일한 결과를 보장.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from app.models.dto import RoomDetail, RoomAvailability
from app.crawler.dream_checker import DreamCrawler


@pytest.fixture
def sample_dream_rooms():
    """테스트용 드림합주실 RoomDetail 목록

    Rationale:
        get_rooms_by_criteria(DB 호출)에 의존하면 DB 데이터 유무에 따라
        테스트가 불안정해짐(IndexError). 하드코딩된 Mock 데이터로 대체.
    """
    rooms = []
    for i in range(1, 6):
        rooms.append(RoomDetail(
            name=f"드림 {i}룸",
            branch="드림합주실 사당점",
            business_id="dream_sadang",
            biz_item_id=str(i),
            imageUrls=[],
            maxCapacity=6,
            recommend_capacity_range=[2, 4],
            pricePerHour=15000,
            canReserveOneHour=True,
            requiresContactOnSameDay=False
        ))
    return rooms


def _make_mock_response(available_times: list[str], date: str):
    """드림 연습실 API 응답을 모방하는 Mock Response 생성 헬퍼

    Args:
        available_times: 예약 가능한 시간 목록 (예: ["13시00분", "14시00분"])
        date: 대상 날짜 (예: "2026-02-14", 현재는 title에 사용되지 않음)

    Rationale:
        실제 드림 연습실 API는 JSON 내 'items' 키에 HTML 문자열을 반환함.
        BeautifulSoup 파싱 로직까지 검증하기 위해 실제 응답 구조를 모방.

        실제 title 형식: "22시00분 ~ 23시00분  최대 15명 예약가능"
        파싱 로직은 t.startswith(target_time)으로 시작 시간을 기준으로 매칭하므로
        title이 반드시 해당 시간으로 시작해야 함.
    """
    def _next_hour(time_str: str) -> str:
        """"13시00분" -> "14시00분" (24시 -> "00시00분")"""
        hour = int(time_str.replace("시00분", ""))
        return f"{(hour + 1) % 24:02d}시00분"

    labels = ""
    for time_str in available_times:
        next_time = _next_hour(time_str)
        labels += (
            f'<label class="btn-time active" title="{time_str} ~ {next_time}  최대 15명 예약가능">'
            f'{time_str}</label>\n'
        )
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"items": labels}
    return mock_resp


@pytest.mark.asyncio
async def test_get_dream_availability(sample_dream_rooms):
    """드림 크롤러가 예약 가능/불가능 상태를 정상 파싱하는지 검증"""
    date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    hour_slots = ["13:00", "14:00"]
    crawler = DreamCrawler()

    # NOTE: 모든 룸에 대해 13시, 14시 모두 예약 가능한 응답 반환
    mock_response = _make_mock_response(["13시00분", "14시00분"], date)

    with patch("app.crawler.dream_checker.load_client", new_callable=AsyncMock, return_value=mock_response):
        result = await crawler.check_availability(date, hour_slots, sample_dream_rooms)

    assert isinstance(result, list)
    assert len(result) == 5

    for room_result in result:
        assert isinstance(room_result, RoomAvailability)
        assert room_result.available is True
        assert room_result.available_slots["13:00"] is True
        assert room_result.available_slots["14:00"] is True


@pytest.mark.asyncio
async def test_dream_partial_availability(sample_dream_rooms):
    """일부 시간만 예약 가능한 경우 올바르게 파싱되는지 검증"""
    date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    hour_slots = ["13:00", "14:00"]
    crawler = DreamCrawler()

    # NOTE: 13시만 가능, 14시는 불가능한 응답
    mock_response = _make_mock_response(["13시00분"], date)

    with patch("app.crawler.dream_checker.load_client", new_callable=AsyncMock, return_value=mock_response):
        result = await crawler.check_availability(date, hour_slots, sample_dream_rooms[:1])

    room_result = result[0]
    assert isinstance(room_result, RoomAvailability)
    assert room_result.available is False  # 일부만 가능하면 False
    assert room_result.available_slots["13:00"] is True
    assert room_result.available_slots["14:00"] is False


@pytest.mark.asyncio
async def test_dream_beyond_date_limit(sample_dream_rooms):
    """예약 한도(121일) 초과 시 HTTP 요청 없이 즉시 예약 불가(False)로 반환되는지 검증

    Rationale:
        드림합주실 예약 폼이 121일 이내만 지원하므로, 초과한 날짜는 예약 시스템이
        지원하지 않는 것으로 간주하여 예약 불가(False) 처리함.
    """
    date = (datetime.now() + timedelta(days=121)).strftime("%Y-%m-%d")
    hour_slots = ["13:00", "14:00"]
    crawler = DreamCrawler()

    # NOTE: 날짜 한도 초과 시 HTTP 요청 없이 즉시 False 반환
    result = await crawler.check_availability(date, hour_slots, sample_dream_rooms[:1])

    room_result = result[0]
    assert room_result.available is False
    assert room_result.available_slots["13:00"] is False
    assert room_result.available_slots["14:00"] is False

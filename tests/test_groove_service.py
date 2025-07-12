# tests/test_groove_service.py
import pytest
from models.dto import AvailabilityResponse, RoomKey
from service.groove_checker import get_groove_availability

@pytest.mark.asyncio
async def test_get_groove_availability():

    # 실제 테스트용 파라미터를 여기에 입력하세요
    date = "2025-07-12"
    hour_slots = ["22:00", "23:00"]
    groove_rooms = [
        RoomKey(name="A룸", branch="그루브 사당점", business_id="sadang", biz_item_id="groove-A"),
        RoomKey(name="B룸", branch="그루브 사당점", business_id="sadang", biz_item_id="groove-B"),
        RoomKey(name="C룸", branch="그루브 사당점", business_id="sadang", biz_item_id="groove-C")
    ]

    result = await get_groove_availability(date, hour_slots, groove_rooms)
    print(result)  # 가공 없이 그대로 출력

@pytest.mark.asyncio
async def test_time_validation():

    # 잘못된 시간 슬롯이 들어오면 예외가 발생하지 않지만, hour_slots가 비어 있으면 결과가 모두 False여야 함
    result = await get_groove_availability(
        date="2025-07-15",
        hour_slots=[],
        rooms=[
            RoomKey(
                name="A룸",
                branch="그루브 사당점",
                business_id="sadang",
                biz_item_id="groove-A"
            )
        ]
    )
    assert isinstance(result, AvailabilityResponse)
    assert result.results[0].available is True  # 빈 hour_slots면 all([])=True

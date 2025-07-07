# tests/test_naver_checker.py
import pytest
import asyncio
from service.naver_checker import get_naver_availability
from models.dto import RoomKey

@pytest.mark.asyncio
async def test_get_naver_availability():
    # 실제 테스트용 파라미터를 여기에 입력하세요
    date = "2025-07-12"
    hour_slots = ["15:00", "16:00", "17:00"]
    naver_rooms = [
        RoomKey(name="Classic", branch="비쥬합주실 3호점", business_id="917236", biz_item_id="5098039"),
        RoomKey(name="화이트룸", branch="비쥬합주실 1호점", business_id="522011", biz_item_id="3968896"),
        RoomKey(name="R룸", branch="준사운드 사당점", business_id="1384809", biz_item_id="6649826"),
    ]

    result = await get_naver_availability(date, hour_slots, naver_rooms)
    print(result)  # 가공 없이 그대로 출력

    # (선택) 간단한 검증도 추가 가능
    assert isinstance(result, list)
    assert all(hasattr(r, "available_slots") for r in result)

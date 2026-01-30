# te/test_naver_checker.py
import pytest

from datetime import datetime, timedelta
from app.crawler.naver_checker import NaverCrawler
from app.models.dto import RoomDetail
from app.utils.room_loader import get_rooms_by_capacity

@pytest.mark.asyncio
async def test_get_naver_availability():
    # 실제 테스트용 파라미터를 여기에 입력하세요
    date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    hour_slots = ["15:00", "16:00", "17:00"]
    naver_rooms = []
    for item in get_rooms_by_capacity(1):
        if item.branch != "그루브 사당점" and item.branch != "드림합주실 사당점":
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
            naver_rooms.append(room)

    crawler = NaverCrawler()
    result = await crawler.check_availability(date, hour_slots, naver_rooms)
    print(result)  # 가공 없이 그대로 출력

    # (선택) 간단한 검증도 추가 가능
    assert isinstance(result, list)
    assert all(hasattr(r, "available_slots") for r in result)

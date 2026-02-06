import pytest
from datetime import datetime, timedelta
from app.models.dto import RoomDetail
from app.models.dto import RoomAvailability
from app.crawler.dream_checker import DreamCrawler
from app.utils.room_loader import get_rooms_by_criteria

@pytest.mark.asyncio
async def test_get_dream_availability():
    date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    rooms = []
    for item in get_rooms_by_criteria(capacity=1):
        if item.branch == "드림합주실 사당점":
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
    hour_slots = ["13:00", "14:00"]
    crawler = DreamCrawler()
    result = await crawler.check_availability(date, hour_slots, rooms)
    # ✅ 결과가 리스트인지 확인
    assert isinstance(result, list)
    assert len(result) == 5

    # ✅ 각 요소에 필요한 키가 들어있는지 확인
    for room_result in result:
        assert isinstance(room_result, RoomAvailability)

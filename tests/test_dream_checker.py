import pytest
from datetime import datetime, timedelta
from app.models.dto import RoomKey
from app.models.dto import RoomAvailability
from app.crawler.dream_checker import get_dream_availability

@pytest.mark.asyncio
async def test_get_dream_availability():
    date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    rooms = [
            RoomKey(name="D룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="29"),
            RoomKey(name="C룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="28"),
            RoomKey(name="Q룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="27"),
            RoomKey(name="S룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="26"),
            RoomKey(name="V룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="25"),
        ]
    hour_slots = ["13:00", "14:00"]
    result = await get_dream_availability(date, hour_slots, rooms)
    assert isinstance(result, list)
    assert len(result) == 5

    for room_result in result:
        assert isinstance(room_result, RoomAvailability)

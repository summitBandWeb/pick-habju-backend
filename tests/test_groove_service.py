import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from models.dto import RoomKey
from exception.groove_exception import GrooveLoginError, GrooveCredentialError
from exception.common_exception import InvalidHourSlotError, InvalidRoomKeyError, InvalidDateFormatError
from service.groove_checker import get_groove_availability

# 테스트용 RoomKey 예시 클래스 (실제 환경에서는 models.dto.RoomKey 사용)
class RoomKey:
    def __init__(self, name, branch, business_id, biz_item_id):
        self.name = name
        self.branch = branch
        self.business_id = business_id
        self.biz_item_id = biz_item_id

@pytest.mark.asyncio
async def test_invalid_date_format():
    with pytest.raises(InvalidDateFormatError):
        await get_groove_availability("2025/07/03", ["15:00", "16:00"], [RoomKey("A룸", "그루브 사당점", "sadang", "13")])

@pytest.mark.asyncio
async def test_past_date():
    with pytest.raises(InvalidDateFormatError):
        await get_groove_availability("2025-07-13", ["15:00", "16:00"], [RoomKey("A룸", "그루브 사당점", "sadang", "13")])

@pytest.mark.asyncio
async def test_invalid_hour_slot_format():
    with pytest.raises(InvalidHourSlotError):
        await get_groove_availability("2025-07-15", ["15", "16:00"], [RoomKey("A룸", "그루브 사당점", "sadang", "13")])

@pytest.mark.asyncio
async def test_past_hour_slot_today():
    from datetime import datetime, timedelta
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    past_hour = (now - timedelta(hours=1)).strftime("%H:%M")
    with pytest.raises(InvalidHourSlotError):
        await get_groove_availability(today, [past_hour, now.strftime("%H:%M")], [RoomKey("A룸", "그루브 사당점", "sadang", "13")])

@pytest.mark.asyncio
async def test_invalid_room_key():
    with pytest.raises(InvalidRoomKeyError):
        await get_groove_availability("2025-07-15", ["15:00", "16:00"], [RoomKey("X룸", "그루브 사당점", "sadang", "99")])

@pytest.mark.asyncio
async def test_empty_rooms():
    with pytest.raises(ValueError):
        await get_groove_availability("2025-07-15", ["15:00", "16:00"], [])

@pytest.mark.asyncio
async def test_groove_credential_error():
    with patch("utils.login.LoginManager.login", new_callable=AsyncMock) as mock_login:
        mock_login.side_effect = Exception(GrooveCredentialError)  # 실제로는 GrooveCredentialError
        with pytest.raises(Exception):
            await get_groove_availability("2025-07-15", ["15:00", "16:00"], [RoomKey("A룸", "그루브 사당점", "sadang", "13")])

@pytest.mark.asyncio
async def test_groove_login_error():
    with patch("utils.login.LoginManager.login", new_callable=AsyncMock) as mock_login:
        mock_login.side_effect = Exception(GrooveLoginError)  # 실제로는 GrooveLoginError
        with pytest.raises(Exception):
            await get_groove_availability("2025-07-15", ["15:00", "16:00"], [RoomKey("A룸", "그루브 사당점", "sadang", "13")])

@pytest.mark.asyncio
async def test_get_groove_availability():

    # 실제 테스트용 파라미터를 여기에 입력하세요
    date = "2025-07-16"
    hour_slots = ["20:00", "23:00"]
    groove_rooms = [
        RoomKey(name="A룸", branch="그루브 사당점", business_id="sadang", biz_item_id="13"),
        RoomKey(name="B룸", branch="그루브 사당점", business_id="sadang", biz_item_id="14"),
        RoomKey(name="C룸", branch="그루브 사당점", business_id="sadang", biz_item_id="15")
    ]

    result = await get_groove_availability(date, hour_slots, groove_rooms)
    print(result)  # 가공 없이 그대로 출력
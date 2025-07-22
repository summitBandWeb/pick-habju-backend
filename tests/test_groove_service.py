import pytest
from datetime import datetime, timedelta

from exception.groove_exception import GrooveLoginError, GrooveCredentialError
from models.dto import RoomKey
from service.groove_checker import get_groove_availability
from utils.room_loader import load_rooms

@pytest.mark.asyncio
async def test_get_groove_availability():
    date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    hour_slots = ["20:00", "21:00", "22:00", "23:00"]
    groove_rooms = []
    for item in load_rooms():
        if item.get("branch") == "그루브 사당점":
            room = RoomKey(
                name=item["name"],
                branch=item["branch"],
                business_id=item["business_id"],
                biz_item_id=item["biz_item_id"]
            )
            groove_rooms.append(room)

    result = await get_groove_availability(date, hour_slots, groove_rooms)
    print(result)  # 가공 없이 그대로 출력

@pytest.mark.asyncio
async def test_groove_login_error():
    with pytest.raises(GrooveLoginError) as exc_info:
        raise GrooveLoginError()
    assert exc_info.value.error_code == "Login-001"
    assert exc_info.value.message == "로그인 중 문제가 발생했습니다. 서버 오류!"
    assert exc_info.value.status_code == 500

@pytest.mark.asyncio
async def test_groove_credential_error():
    with pytest.raises(GrooveCredentialError) as exc_info:
        raise GrooveCredentialError()
    assert exc_info.value.error_code == "Login-002"
    assert exc_info.value.message == "로그인 중 문제가 발생했습니다. 환경 설정이 필요합니다 Login, Password"
    assert exc_info.value.status_code == 401

from typing import List
from bs4 import BeautifulSoup
import httpx
from config import GROOVE_RESERVE_URL1, GROOVE_RESERVE_URL
from utils.login import LoginManager
from models.dto import RoomAvailability, RoomKey
from datetime import datetime, timedelta
from exception.groove_exception import GrooveLoginError, GrooveCredentialError

import asyncio

# --- Validation 함수 import ---
from utils.validate.common_validator import (
    validate_date,
    validate_hour_slots,
    validate_room_key
)
# your_validation_module은 validate_date, validate_hour_slots, validate_room_key가 정의된 파일명으로 바꿔주세요.

async def fetch_room_availability(room: RoomKey, hour_slots: list, soup: BeautifulSoup) -> RoomAvailability:
    # RoomKey 유효성 검사
    validate_room_key(room)
    rm_ix = room.biz_item_id
    # 구간 계산: 예) ["23:00", "05:00"] → 23:00~00:00, ..., 04:00~05:00
    start = datetime.strptime(hour_slots[0], "%H:%M")
    end = datetime.strptime(hour_slots[1], "%H:%M")
    slots = {}
    curr = start
    while True:
        hour_str = curr.strftime("%H:%M")
        hour_int = curr.hour
        selector = f'#reserve_time_{rm_ix}_{hour_int}.reserve_time_off'
        elem = soup.select_one(selector)
        slots[hour_str] = bool(elem)
        curr += timedelta(hours=1)
        if curr.time() == end.time():
            break
    overall = all(slots.values())
    return RoomAvailability(
        name=room.name,
        branch=room.branch,
        business_id=room.business_id,
        biz_item_id=room.biz_item_id,
        available=overall,
        available_slots=slots
    )

async def get_groove_availability(
    date: str,
    hour_slots: List[str],
    rooms: List[RoomKey]
) -> List[RoomAvailability]:
    # --- 입력값 검증 ---
    validate_date(date)
    validate_hour_slots(hour_slots, date)
    if not rooms:
        raise ValueError("rooms 리스트는 비어 있을 수 없습니다.")
    for room in rooms:
        validate_room_key(room)
    # --- 예약 정보 조회 ---
    try:
        async with httpx.AsyncClient() as client:
            await LoginManager.login(client)
            resp = await client.post(
                GROOVE_RESERVE_URL,
                data={"reserve_date": date, "gubun": "sadang"},
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": GROOVE_RESERVE_URL1
                }
            )
    except GrooveCredentialError as e:
        # 환경 변수 미설정 등 자격증명 오류 처리
        # 필요시 로깅 및 사용자 친화적 메시지 반환
        raise
    except GrooveLoginError as e:
        # 로그인 실패 처리
        # 필요시 로깅 및 사용자 친화적 메시지 반환
        raise

    soup = BeautifulSoup(resp.text, "html.parser")
    tasks = [fetch_room_availability(room, hour_slots, soup) for room in rooms]
    results = await asyncio.gather(*tasks)
    return results

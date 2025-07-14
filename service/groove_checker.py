from typing import List
from bs4 import BeautifulSoup
import httpx
from config import GROOVE_RESERVE_URL1, GROOVE_RESERVE_URL
from utils.login import LoginManager
from models.dto import RoomAvailability, RoomKey
from datetime import datetime, timedelta
import asyncio

async def fetch_room_availability(room: RoomKey, hour_slots: list, soup: BeautifulSoup) -> RoomAvailability:
    rm_ix = room.biz_item_id
    # 입력 예시: ["20:00", "23:00"]
    # 구간: 20:00~21:00, 21:00~22:00, 22:00~23:00
    start = datetime.strptime(hour_slots[0], "%H:%M")
    end = datetime.strptime(hour_slots[1], "%H:%M")
    slots = {}
    curr = start
    while curr < end:
        hour_str = curr.strftime("%H:%M")
        hour_int = curr.hour
        selector = f'#reserve_time_{rm_ix}_{hour_int}.reserve_time_off'
        elem = soup.select_one(selector)
        slots[hour_str] = bool(elem)
        curr += timedelta(hours=1)
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

    soup = BeautifulSoup(resp.text, "html.parser")
    # 각 방별로 병렬 처리
    tasks = [fetch_room_availability(room, hour_slots, soup) for room in rooms]
    results = await asyncio.gather(*tasks)
    return results

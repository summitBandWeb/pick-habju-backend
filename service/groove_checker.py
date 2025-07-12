from typing import List
from bs4 import BeautifulSoup
import httpx
from config import GROOVE_BASE_URL, GROOVE_RESERVE_URL
from utils.login import LoginManager
from models.dto import RoomAvailability,AvailabilityResponse,RoomKey
# A,B,C,D → 13,14,15,16 매핑
RM_IX_MAP = {
    "A": "13",
    "B": "14",
    "C": "15",
    "D": "16",
}

async def get_groove_availability(
    date: str,
    hour_slots: List[str],
    rooms: List[RoomKey]
) -> AvailabilityResponse:
    async with httpx.AsyncClient() as client:
        await LoginManager.login(client)
        resp = await client.post(
            GROOVE_RESERVE_URL,
            data={"reserve_date": date, "gubun": "sadang"},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{GROOVE_BASE_URL}/reservation/reserve.asp"
            }
        )

    soup = BeautifulSoup(resp.text, "html.parser")
    results: List[RoomAvailability] = []
    available_biz_item_ids: List[str] = []

    for room in rooms:
        last = room.biz_item_id.split("-")[-1]
        rm_ix = RM_IX_MAP.get(last)
        if rm_ix is None:
            continue
        # 매핑 오류
        slots = {t: False for t in hour_slots}
        for hour_str in hour_slots:
            hour_int = int(hour_str.split(":")[0])
            selector = f'#reserve_time_{rm_ix}_{hour_int}.reserve_time_off'
            elem = soup.select_one(selector)
            if elem:
                slots[hour_str] = True

        overall = all(slots.values())
        if overall:
            available_biz_item_ids.append(room.biz_item_id)

        results.append(RoomAvailability(
            name=room.name,
            branch=room.branch,
            business_id=room.business_id,
            biz_item_id=room.biz_item_id,
            available=overall,
            available_slots=slots
        ))

    return AvailabilityResponse(
        date=date,
        hour_slots=hour_slots,
        results=results,
        available_biz_item_ids=available_biz_item_ids
    )

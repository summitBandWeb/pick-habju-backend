from bs4 import BeautifulSoup
import html
import sys
import asyncio
from datetime import datetime
from app.models.dto import RoomKey, RoomAvailability
from app.utils.client_loader import load_client
from typing import List, Union

from app.exception.crawler.dream_exception import DreamAvailabilityError

sys.stdout.reconfigure(encoding='utf-8')

_URL = "https://www.xn--hy1bm6g6ujjkgomr.com/plugin/wz.bookingT1.prm/ajax.calendar.time.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded"
}

DATE_LIMIT_DAYS = 121
RoomResult = Union[RoomAvailability, Exception]

async def _fetch_dream_availability_room(date: str, hour_slots: List[str], room: RoomKey) -> RoomAvailability:
    data = {
        'rm_ix': room.biz_item_id,
        'sch_date': date
    }

    response = await load_client(_URL, headers=HEADERS, data=data)

    try:
        response_data = response.json()
    except Exception as e:
       raise DreamAvailabilityError(f"[{room.name}] JSON 파싱 오류: {e}")

    try:
        items_html = html.unescape(response_data.get("items", ""))
    except Exception as e:
        raise DreamAvailabilityError(f"[{room.name}] 응답 아이템 읽기 오류: {e}")

    # BeautifulSoup으로 파싱
    soup = BeautifulSoup(items_html, "html.parser")
    available_slots = {}

    for time in hour_slots:
        target_time = time.split(":")[0] + "시00분" # 예: "14:00" -> "14시00분"
        
        # title 속성에 target_time이 포함된 label 태그 찾기
        # 예: title="2024-05-20 14시00분 (월)"
        label = soup.find('label', title=lambda t: t and target_time in t)
        
        if label:
            # class 속성에 'active'가 있으면 예약 가능
            classes = label.get("class", [])
            available_slots[time] = "active" in classes
        else:
            available_slots[time] = False

    available = all(available_slots.values())

    return RoomAvailability(
        name=room.name,
        branch=room.branch,
        business_id=room.business_id,
        biz_item_id=room.biz_item_id,
        available=available,
        available_slots=available_slots
    )

async def get_dream_availability(
      date: str,
      hour_slots: List[str],
      dream_rooms: List[RoomKey]
) -> List[RoomResult]:

    today = datetime.strptime(datetime.now().strftime('%Y-%m-%d'), '%Y-%m-%d').date()
    target_date = datetime.strptime(date, '%Y-%m-%d').date()

    if (target_date - today).days >= DATE_LIMIT_DAYS:
        return [
            RoomAvailability(
                name=room.name,
                branch=room.branch,
                business_id=room.business_id,
                biz_item_id=room.biz_item_id,
                available="unknown",
                available_slots={hour_str: "unknown" for hour_str in hour_slots},
            )
            for room in dream_rooms
        ]

    async def safe_fetch(room: RoomKey) -> RoomResult:
        # --- 제거됨: RoomKey 검증은 메인 라우터에서 처리됩니다 ---
        try:
            return await _fetch_dream_availability_room(date, hour_slots, room)
        except DreamAvailabilityError as e:
            # 호출자에 의해 로깅될 예외를 반환
            return e

    return await asyncio.gather(*[safe_fetch(room) for room in dream_rooms])

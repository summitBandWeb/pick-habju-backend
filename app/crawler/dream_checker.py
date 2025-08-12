import re
import html
import sys
import asyncio
import datetime
from app.utils.room_loader import load_rooms
from app.models.dto import RoomKey
from app.models.dto import RoomAvailability
from app.utils.client_loader import load_client
from typing import List, Union

from app.exception.crawler.dream_exception import DreamAvailabilityError
from app.validate.date_validator import validate_date
from app.validate.hour_validator import validate_hour_slots
from app.validate.roomkey_validator import validate_room_key


sys.stdout.reconfigure(encoding='utf-8')

_URL = "https://www.xn--hy1bm6g6ujjkgomr.com/plugin/wz.bookingT1.prm/ajax.calendar.time.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded"
}

date_limit = 121
RoomResult = Union[RoomAvailability, Exception]
available = Union[bool, str]

async def get_dream_availability(
      date: str,
      hour_slots: List[str],
      dream_rooms: List[RoomKey]
) -> List[RoomAvailability]:
    validate_date(date)
    validate_hour_slots(hour_slots, date)

    today = datetime.date.today()
    input_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

    if (input_date - today).days > date_limit:
        # 모든 room에 대해 "unknown" RoomAvailability 생성
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


    return await asyncio.gather(*[safe_fetch(date, hour_slots, room) for room in dream_rooms])

async def safe_fetch(date, hour_slots, room: RoomKey) -> RoomResult:
    validate_room_key(room)
    return await _fetch_dream_availability_room(date, hour_slots, room)


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
        available = True
        available_slots = {}
        items_html = html.unescape(response_data.get("items", ""))
    except Exception as e:
        raise DreamAvailabilityError()

    for time in hour_slots:
        # 1. 타임 포맷 변환
        try:
            target_time = time.split(":")[0] + "시00분"
        except Exception as e:
            raise DreamAvailabilityError(f"[{room.name}] 시간 포맷 파싱 오류: {e}")

        # 2. 정규표현식 생성
        try:
            pattern = fr'<label class="([^"]+)" title="{re.escape(target_time)}[^"]*">'
        except re.error as e:
            raise DreamAvailabilityError(f"[{room.name}] 정규표현식 컴파일 오류: {e}")

        # 3. 정규표현식 검색
        try:
            match = re.search(pattern, items_html, re.DOTALL)
        except Exception as e:
            raise DreamAvailabilityError(f"[{room.name}] 정규표현식 검색 오류: {e}")

        # 4. 매칭 결과 처리
        try:
            if match:
                classes = match.group(1).split()
                available_slots[time] = True if 'active' in classes else False
            else:
                available_slots[time] = False

            if not available_slots[time]:
                available = False
        except Exception as e:
            raise DreamAvailabilityError(f"[{room.name}] 매칭 후 처리 오류: {e}")

    try:
        rooms = load_rooms()
    except Exception as e: #난슬이가 만든 에러 넣기
        raise

    # 2. 매칭 필터링
    try:
        matches = [
            (r["name"], r["branch"], r["business_id"])
            for r in rooms
            if str(r["biz_item_id"]) == str(room.biz_item_id)
        ]
    except KeyError as e:
        raise DreamAvailabilityError(f"[{room.name}] rooms 항목에 필요한 키 없음: {e}")
    except Exception as e:
        raise DreamAvailabilityError(f"[{room.name}] rooms 필터링 중 오류: {e}")

    # 3. 매칭 결과 해체
    try:
        if matches:
            name, branch, business_id = matches[0]
        else:
            raise DreamAvailabilityError(f"[{room.name}] 일치하는 room 정보를 찾을 수 없음")
    except Exception as e:
        raise DreamAvailabilityError(f"[{room.name}] room 정보 분해 오류: {e}")

    return RoomAvailability(
        name=name,
        branch=branch,
        business_id=business_id,
        biz_item_id=room.biz_item_id,
        available=available,
        available_slots=available_slots,
    )

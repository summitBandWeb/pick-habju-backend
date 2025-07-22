import httpx
import re
import html
import sys
import asyncio
from utils.room_loader import load_rooms
from models.dto import RoomKey
from models.dto import RoomAvailability
from utils.client_loader import load_client
from typing import List, Union

from exception.dream_exception import DreamAvailabilityError
from utils.validate.common.date_validator import (validate_date, InvalidDateFormatError, PastDateNotAllowedError)
from utils.validate.common.hour_validator import (validate_hour_slots, InvalidHourSlotError, PastHourSlotNotAllowedError)
from utils.validate.common.response_validator import ResponseMismatchError
from utils.validate.common.roomkey_validator import (validate_room_key, RoomKeyNotFoundError, RoomKeyFieldMissingError)
from exception.utils.client_loader_exception import RequestFailedError


sys.stdout.reconfigure(encoding='utf-8')

_URL = "https://www.xn--hy1bm6g6ujjkgomr.com/plugin/wz.bookingT1.prm/ajax.calendar.time.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded"
}

RoomResult = Union[RoomAvailability, Exception]

async def get_dream_availability(
      date: str, 
      hour_slots: List[str], 
      dream_rooms: List[RoomKey]
) -> List[RoomAvailability]:
   try:
      validate_date(date)
   except InvalidDateFormatError as e:
      print(f"[날짜 형식 오류]: {e}")
      raise
   except PastDateNotAllowedError as e:
       raise
   
   try:
      validate_hour_slots(hour_slots)
   except InvalidHourSlotError as e:
      print(f"[시간 형식 오류]: {e}")
      raise
   except PastHourSlotNotAllowedError as e:
       raise
   
   return await asyncio.gather(*[safe_fetch(date, hour_slots, room.biz_item_id) for room in dream_rooms])

async def safe_fetch(date, hour_slots, room: RoomKey) -> RoomResult:
      try:
         validate_room_key(room)
      except RoomKeyNotFoundError as e:
         raise
      except RoomKeyFieldMissingError as e:
         raise
      
      try:
          return await _fetch_dream_availability_room(date, hour_slots, room)
      except DreamAvailabilityError as e:
          raise

async def _fetch_dream_availability_room(date: str, hour_slots: List[str], biz_item_id: RoomKey) -> RoomAvailability:
    data = {
        'rm_ix': biz_item_id,
        'sch_date': date    
    }

    try:
        response = await load_client(_URL, headers=HEADERS, data=data)
    except RequestFailedError as e:
        raise

    try:    
        response_data = response.json()
    except Exception as e:
       raise DreamAvailabilityError(f"[{biz_item_id.name}] JSON 파싱 오류: {e}")

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
            raise DreamAvailabilityError(f"[{biz_item_id.name}] 시간 포맷 파싱 오류: {e}")

        # 2. 정규표현식 생성
        try:
            pattern = fr'<label class="([^"]+)" title="{re.escape(target_time)}[^"]*">'
        except re.error as e:
            raise DreamAvailabilityError(f"[{biz_item_id.name}] 정규표현식 컴파일 오류: {e}")

        # 3. 정규표현식 검색
        try:
            match = re.search(pattern, items_html, re.DOTALL)
        except Exception as e:
            raise DreamAvailabilityError(f"[{biz_item_id.name}] 정규표현식 검색 오류: {e}")

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
            raise DreamAvailabilityError(f"[{biz_item_id.name}] 매칭 후 처리 오류: {e}")    
    
    try:
        rooms = load_rooms()
    except Exception as e: #난슬이가 만든 에러 넣기
        raise

    # 2. 매칭 필터링
    try:
        matches = [
            (r["name"], r["branch"], r["business_id"])
            for r in rooms
            if r["biz_item_id"] == biz_item_id
        ]
    except KeyError as e:
        raise DreamAvailabilityError(f"[{biz_item_id.name}] rooms 항목에 필요한 키 없음: {e}")
    except Exception as e:
        raise DreamAvailabilityError(f"[{biz_item_id.name}] rooms 필터링 중 오류: {e}")

    # 3. 매칭 결과 해체
    try:
        if matches:
            name, branch, business_id = matches[0]
        else:
            raise DreamAvailabilityError(f"[{biz_item_id.name}] 일치하는 room 정보를 찾을 수 없음")
    except Exception as e:
        raise DreamAvailabilityError(f"[{biz_item_id.name}] room 정보 분해 오류: {e}")

    return RoomAvailability(name = name, branch = branch, business_id=business_id, biz_item_id=biz_item_id, available=available, available_slots=available_slots)
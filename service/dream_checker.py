import httpx
import re
import html
import sys
import asyncio
from utils.room_loader import load_rooms
from models.dto import RoomKey
from models.dto import RoomAvailability
from typing import List, Union

from exception.dream_exception import DreamAvailabilityError
from utils.validate.common_validator import (
    validate_date, validate_hour_slots, validate_room_key,  InvalidDateFormatError,
    InvalidHourSlotError,
    InvalidRoomKeyError,
)


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
   
   try:
      validate_hour_slots(hour_slots)
   except InvalidHourSlotError as e:
      print(f"[시간 형식 오류]: {e}")
      raise

   async def safe_fetch(room: RoomKey) -> RoomResult:
      try:
         validate_room_key(room)
         return await _fetch_dream_availability_room(date, hour_slots, room)
      except (InvalidRoomKeyError, DreamAvailabilityError) as e:
         return e
      
   return await asyncio.gather(*[safe_fetch(room.biz_item_id) for room in dream_rooms])

async def _fetch_dream_availability_room(date: str, hour_slots: List[str], biz_item_id: RoomKey) -> RoomAvailability:
    data = {
        'rm_ix': biz_item_id,
        'sch_date': date
    }

    async with httpx.AsyncClient() as client:
      response = await client.post(_URL, headers=HEADERS, data=data)
      response_data = response.json()

    available = True
    available_slots = {}
    items_html = html.unescape(response_data.get("items", ""))
    try:   
      for time in hour_slots:
        target_time = time.split(":")[0] + "시00분"
        pattern = fr'<label class="([^"]+)" title="{re.escape(target_time)}[^"]*">'
        match = re.search(pattern, items_html, re.DOTALL)

        if match:
            classes = match.group(1).split()
            available_slots[time] = True if 'active' in classes else False
        else:
            available_slots[time] = False

        if available_slots[time] == False:
          available = False  
    except Exception as e:
       raise DreamAvailabilityError(f"[{biz_item_id.name}] 응답 파싱 오류: {e}")
    
    rooms = load_rooms()
    matches = [ (r["name"], r["branch"], r["business_id"]) for r in rooms if r["biz_item_id"] == biz_item_id]
    if matches:
       name, branch, business_id = matches[0]
    
    return RoomAvailability(name = name, branch = branch, business_id=business_id, biz_item_id=biz_item_id, available=available, available_slots=available_slots)
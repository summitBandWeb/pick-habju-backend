import httpx
from typing import List, Dict, Union

from app.exception.common.date_exception import InvalidDateFormatError
from app.exception.common.hour_excpetion import InvalidHourSlotError
from app.models.dto import RoomKey, RoomAvailability
from app.exception.naver_exception import NaverAvailabilityError

import asyncio

from app.validate.date_validator import validate_date
from app.validate.hour_validator import validate_hour_slots
from app.validate.roomkey_validator import validate_room_key

RoomResult = Union[RoomAvailability, Exception]

async def fetch_naver_availability_room(date: str, hour_slots: List[str], room: RoomKey) -> RoomAvailability:
    url = "https://booking.naver.com/graphql?opName=schedule"
    start_dt = f"{date}T00:00:00"
    end_dt = f"{date}T23:59:59"
    headers = {"Content-Type": "application/json"}
    body = {
        "operationName": "schedule",
        "query": """
        query schedule($scheduleParams: ScheduleParams) {
          schedule(input: $scheduleParams) {
            bizItemSchedule {
              hourly {
                unitStartTime
                unitStock
                unitBookingCount
              }
            }
          }
        }""",
        "variables": {
            "scheduleParams": {
                "businessTypeId": 10,
                "businessId": room.business_id,
                "bizItemId": room.biz_item_id,
                "startDateTime": start_dt,
                "endDateTime": end_dt,
                "fixedTime": True,
                "includesHolidaySchedules": True
            }
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            raise NaverAvailabilityError(f"[{room.name}] 네이버 API 호출 오류: {e}")

    try:
        available_slots: Dict[str, bool] = {}
        for slot in data["data"]["schedule"]["bizItemSchedule"]["hourly"]:
            time_str = slot["unitStartTime"][-8:]
            hour_min = time_str[:5]
            if hour_min in hour_slots:
                available_slots[hour_min] = slot["unitBookingCount"] < slot["unitStock"]
    except Exception as e:
        raise NaverAvailabilityError(f"[{room.name}] 응답 파싱 오류: {e}")

    available = all(available_slots.values())
    return RoomAvailability(
        name=room.name,
        branch=room.branch,
        business_id=room.business_id,
        biz_item_id=room.biz_item_id,
        available=available,
        available_slots=available_slots
    )


async def get_naver_availability(
    date: str,
    hour_slots: List[str],
    naver_rooms: List[RoomKey]
) -> List[RoomResult]:

    return await asyncio.gather(*[fetch_naver_availability_room(date, hour_slots, room) for room in naver_rooms])

import httpx
from typing import List, Dict
from models.dto import RoomKey, RoomAvailability
import asyncio

async def _fetch_naver_availability_for_room(date: str, hour_slots: List[str], room: RoomKey) -> RoomAvailability:
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
        response = await client.post(url, json=body, headers=headers)
        data = response.json()
    available_slots: Dict[str, bool] = {}
    try:
        for slot in data["data"]["schedule"]["bizItemSchedule"]["hourly"]:
            time_str = slot["unitStartTime"][-8:]  # e.g. "16:00:00"
            hour_min = time_str[:5]               # e.g. "16:00"
            if hour_min in hour_slots:
                available_slots[hour_min] = slot["unitBookingCount"] < slot["unitStock"]
    except Exception:
        # 네이버 응답 구조가 다르거나 오류시 모두 False 처리
        for h in hour_slots:
            available_slots[h] = False
    available = all(available_slots.values())
    return RoomAvailability(
        name=room.name,
        branch=room.branch,
        business_id=room.business_id,
        biz_item_id=room.biz_item_id,
        available=available,
        available_slots=available_slots
    )

async def get_naver_availability(date: str, hour_slots: List[str], naver_rooms: List[RoomKey]) -> List[RoomAvailability]:
    tasks = [
        _fetch_naver_availability_for_room(date, hour_slots, room)
        for room in naver_rooms
    ]
    return await asyncio.gather(*tasks)

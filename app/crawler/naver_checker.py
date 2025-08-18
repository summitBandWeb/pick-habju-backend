import httpx
from typing import List, Dict, Union
from app.models.dto import RoomKey, RoomAvailability
from app.exception.crawler.naver_exception import NaverAvailabilityError, NaverRequestError
from app.exception.api.client_loader_exception import RequestFailedError
from app.utils.client_loader import load_client
import asyncio

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

    try:
        response = await load_client(url, json=body, headers=headers)
        data = response.json()
    except RequestFailedError as e:
        # 공통 클라이언트 계층의 실패를 네이버 전용 예외로 매핑
        raise NaverRequestError(f"[{room.name}] 네이버 API 호출 실패: {e}")
    except Exception as e:
        raise NaverAvailabilityError(f"[{room.name}] 네이버 API 호출/파싱 오류: {e}")

    try:
        api_slots = data.get("data", {}).get("schedule", {}).get("bizItemSchedule", {}).get("hourly", [])
        if api_slots is None:
            api_slots = []

        available_slots: Dict[str, bool] = {slot: False for slot in hour_slots}

        for slot_data in api_slots:
            time_str = slot_data["unitStartTime"][-8:]
            hour_min = time_str[:5]
            if hour_min in available_slots:
                available_slots[hour_min] = slot_data["unitBookingCount"] < slot_data["unitStock"]

    except Exception as e:
        raise NaverAvailabilityError(f"[{room.name}] 응답 파싱 오류: {e}")

    available = all(val for hour, val in available_slots.items() if hour in hour_slots)

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
    # --- 제거됨: 모든 입력값 검증은 이제 메인 라우터에서 처리됩니다 ---

    async def safe_fetch(room: RoomKey) -> RoomResult:
        try:
            return await fetch_naver_availability_room(date, hour_slots, room)
        except NaverAvailabilityError as e:
            return e

    return await asyncio.gather(*[safe_fetch(room) for room in naver_rooms])

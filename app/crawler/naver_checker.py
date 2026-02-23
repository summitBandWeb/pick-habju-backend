import httpx
from typing import List, Dict, Union
import asyncio

from app.models.dto import RoomDetail, RoomAvailability
from app.exception.crawler.naver_exception import NaverAvailabilityError, NaverRequestError
from app.exception.api.client_loader_exception import RequestFailedError
from app.utils.client_loader import load_client
from app.exception.base_exception import BaseCustomException

from app.crawler.base import BaseCrawler, RoomResult
from app.crawler.registry import registry

class NaverCrawler(BaseCrawler):
    async def check_availability(self, date: str, hour_slots: List[str], target_rooms: List[RoomDetail]) -> List[RoomResult]:
        async def safe_fetch(room: RoomDetail) -> RoomResult:
            try:
                return await self._fetch_naver_availability_room(date, hour_slots, room)
            except BaseCustomException as e:
                return e
            except Exception as e:
                # 예상치 못한 에러는 룸 정보를 포함하여 새로운 예외로 반환
                return Exception(f"[{room.name}] Unexpected error: {str(e)}")

        return await asyncio.gather(*[safe_fetch(room) for room in target_rooms])

    async def _fetch_naver_availability_room(self, date: str, hour_slots: List[str], room: RoomDetail) -> RoomAvailability:
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
            room_detail=room,
            available=available,
            available_slots=available_slots
        )

# Register the crawler
registry.register("naver", NaverCrawler())

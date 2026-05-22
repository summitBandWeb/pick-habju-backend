import httpx
from typing import List, Dict, Union
import asyncio
import os

from app.models.dto import RoomDetail, RoomAvailability
from app.exception.crawler.naver_exception import NaverAvailabilityError, NaverRequestError
from app.exception.api.client_loader_exception import RequestFailedError
from app.utils.client_loader import load_client
from app.exception.base_exception import BaseCustomException

from app.crawler.base import BaseCrawler, RoomResult
from app.crawler.registry import registry

class NaverCrawler(BaseCrawler):
    """네이버 예약 GraphQL API를 통해 합주실 예약 가능 여부를 확인하는 크롤러.

    네이버 예약(booking.naver.com)의 schedule GraphQL 엔드포인트를 호출하여
    시간대별 재고(unitStock)와 예약 수(unitBookingCount)를 비교해 가용 여부를 판단한다.
    """

    # 네이버 RATE LIMIT 대응: 동시 API 요청 수를 클래스 수준에서 공유하여 전역 동시성을 제한한다.
    # check_availability 호출마다 새 세마포어를 만들면 호출 간 공유가 되지 않으므로 클래스 속성으로 초기화한다.
    # 높은 부하의 경우 환경 변수(NAVER_CRAWLER_SEMAPHORE)를 통해 조정 가능하도록 지원.
    _semaphore: asyncio.Semaphore = asyncio.Semaphore(max(1, int(os.getenv("NAVER_CRAWLER_SEMAPHORE", "60"))))
    # 프리페치 전용 세마포어: _semaphore와 슬롯을 공유하지 않아 프리페치가 재검색을 블로킹하지 않는다.
    _prefetch_semaphore: asyncio.Semaphore = asyncio.Semaphore(max(1, int(os.getenv("NAVER_PREFETCH_SEMAPHORE", "60"))))

    async def check_availability(self, date: str, hour_slots: List[str], target_rooms: List[RoomDetail], *, prefetch: bool = False) -> List[RoomResult]:
        """네이버 예약 API로 특정 날짜와 시간대에 예약 가능한 방들을 조회한다.

        각 방을 asyncio.gather로 병렬 조회하며, 개별 실패는 Exception 객체로
        안전하게 포획하여 나머지 결과에 영향을 주지 않도록 한다.

        Args:
            date (str): 조회할 날짜 (예: '2026-05-20').
            hour_slots (List[str]): 1시간 단위 시간 슬롯 배열 (예: ['14:00', '15:00']).
            target_rooms (List[RoomDetail]): 조회 대상 방 리스트.
            prefetch (bool): True이면 _prefetch_semaphore를, False(기본값)이면 _semaphore를 사용한다.
                프리페치 요청이 재검색 요청을 블로킹하지 않도록 세마포어를 분리한다.

        Returns:
            List[RoomResult]: 방별 RoomAvailability 또는 에러 Exception 객체 배열.
        """

        async def safe_fetch(room: RoomDetail) -> RoomResult:
            """개별 방 조회를 예외-안전하게 감싸 실패 시 Exception 객체를 반환한다.

            Args:
                room (RoomDetail): 조회할 방 정보.

            Returns:
                RoomResult: 성공 시 RoomAvailability, 실패 시 Exception 객체.
            """
            sem = self._prefetch_semaphore if prefetch else self._semaphore
            async with sem:
                try:
                    return await self._fetch_naver_availability_room(date, hour_slots, room)
                except BaseCustomException as e:
                    return e
                except Exception as e:
                    # 예상치 못한 에러는 룸 정보를 포함하여 새로운 예외로 반환
                    return Exception(f"[{room.name}] Unexpected error: {str(e)}")

        return await asyncio.gather(*[safe_fetch(room) for room in target_rooms])

    async def _fetch_naver_availability_room(self, date: str, hour_slots: List[str], room: RoomDetail) -> RoomAvailability:
        """네이버 schedule GraphQL API를 호출하여 단일 방의 시간대별 예약 가능 여부를 조회한다."""
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
                    isUnitBusinessDay
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
                    has_stock = slot_data["unitBookingCount"] < slot_data["unitStock"]
                    is_open = slot_data.get("isUnitBusinessDay", True)
                    available_slots[hour_min] = has_stock and is_open

        except Exception as e:
            raise NaverAvailabilityError(f"[{room.name}] 응답 파싱 오류: {e}")

        available = self.resolve_tri_state(available_slots, hour_slots)

        return RoomAvailability(
            room_detail=room,
            available=available,
            available_slots=available_slots
        )

# Register the crawler
registry.register("naver", NaverCrawler())

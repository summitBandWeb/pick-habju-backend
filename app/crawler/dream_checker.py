from app.exception.crawler.dream_exception import DreamRequestError
from bs4 import BeautifulSoup
import html
import sys
import asyncio
from datetime import datetime
from typing import List

from app.models.dto import RoomDetail, RoomAvailability
from app.utils.client_loader import load_client
from app.exception.base_exception import BaseCustomException
from app.exception.crawler.dream_exception import DreamAvailabilityError

from app.crawler.base import BaseCrawler, RoomResult
from app.crawler.registry import registry



sys.stdout.reconfigure(encoding='utf-8')

class DreamCrawler(BaseCrawler):
    _URL = "https://www.xn--hy1bm6g6ujjkgomr.com/plugin/wz.bookingT1.prm/ajax.calendar.time.php"
    HEADERS = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    DATE_LIMIT_DAYS = 121  # Reservation window limit per Dream policy.

    async def check_availability(self, date: str, hour_slots: List[str], target_rooms: List[RoomDetail]) -> List[RoomResult]:
        today = datetime.strptime(datetime.now().strftime('%Y-%m-%d'), '%Y-%m-%d').date()
        target_date = datetime.strptime(date, '%Y-%m-%d').date()

        if (target_date - today).days >= self.DATE_LIMIT_DAYS:
            return [
                RoomAvailability(
                    room_detail=room,
                    available="unknown",
                    available_slots={hour_str: "unknown" for hour_str in hour_slots},
                )
                for room in target_rooms
            ]

        async def safe_fetch(room: RoomDetail) -> RoomResult:
            try:
                return await self._fetch_dream_availability_room(date, hour_slots, room)
            except BaseCustomException as e:
                return e
            except Exception as e:
                # 예상치 못한 에러는 룸 정보를 포함하여 새로운 예외로 반환
                return Exception(f"[{room.name}] Unexpected error: {str(e)}")

        return await asyncio.gather(*[safe_fetch(room) for room in target_rooms])

    async def _fetch_dream_availability_room(self, date: str, hour_slots: List[str], room: RoomDetail) -> RoomAvailability:
        data = {
            'rm_ix': room.biz_item_id,
            'sch_date': date
        }

        response = await load_client(self._URL, headers=self.HEADERS, data=data)

        try:
            response_data = response.json()
        except Exception as e:
            raise DreamAvailabilityError(f"[{room.name}] JSON 파싱 오류: {e}")

        try:
            items_html = html.unescape(response_data.get("items", ""))
        except Exception as e:
            raise DreamAvailabilityError(f"[{room.name}] 응답 아이템 읽기 오류: {e}")

        # BeautifulSoup으로 파싱
        available_slots = self._parse_html_content(items_html, hour_slots)
        available = all(available_slots.values())

        return RoomAvailability(
            room_detail=room,
            available=available,
            available_slots=available_slots
        )

    def _parse_html_content(self, items_html: str, hour_slots: List[str]) -> dict:
        """BeautifulSoup을 사용하여 HTML에서 시간대별 예약 가능 여부를 파싱합니다."""
        soup = BeautifulSoup(items_html, "lxml")
        available_slots = {}

        for time in hour_slots:
            target_time = time.split(":")[0] + "시00분"  # 예: "14:00" -> "14시00분"

            # title 속성에 target_time이 포함된 label 태그 찾기
            # 예: title="2024-05-20 14시00분 (월)"
            label = soup.find('label', title=lambda t: t and isinstance(t, str) and target_time in t)

            if label:
                # class 속성에 'active'가 있으면 예약 가능
                classes = label.get("class", [])
                available_slots[time] = "active" in classes
            else:
                available_slots[time] = False

        return available_slots

# Register the crawler
registry.register("dream", DreamCrawler())

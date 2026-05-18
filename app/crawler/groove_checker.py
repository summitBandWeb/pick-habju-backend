import asyncio
import os
from datetime import datetime
from typing import List

import httpx
from bs4 import BeautifulSoup

from app.core.config import GROOVE_RESERVE_URL, GROOVE_RESERVE_URL1
from app.exception.crawler.groove_exception import GrooveCredentialError, GrooveLoginError
from app.utils.login import LoginManager
from app.models.dto import RoomAvailability, RoomDetail

from app.crawler.base import BaseCrawler, RoomResult
from app.crawler.registry import registry

class GrooveCrawler(BaseCrawler):
    """그루브 합주실의 예약 가능 여부를 확인하는 전용 크롤러.

    그루브 합주실은 로그인 기반 자체 예약 폼을 사용하므로,
    LoginManager로 세션을 확보한 뒤 HTML을 파싱하여 예약 정보를 조회한다.
    """

    RESERVATION_LIMIT_DAYS = 84  # Reservation window limit per Groove policy.
    _semaphore: asyncio.Semaphore = asyncio.Semaphore(int(os.getenv("GROOVE_CRAWLER_SEMAPHORE", "10")))
    # 프리페치 전용 세마포어: _semaphore와 슬롯을 공유하지 않아 프리페치가 재검색을 블로킹하지 않는다.
    _prefetch_semaphore: asyncio.Semaphore = asyncio.Semaphore(int(os.getenv("GROOVE_PREFETCH_SEMAPHORE", "10")))

    async def check_availability(self, date: str, hour_slots: List[str], target_rooms: List[RoomDetail], *, prefetch: bool = False) -> List[RoomResult]:
        """그루브 합주실의 특정 날짜와 시간대에 예약 가능한 방들을 조회한다.

        로그인 후 예약 페이지 HTML을 가져와 각 방의 슬롯 상태를 파싱한다.
        예약 가능 기한(84일)을 초과하면 모든 방을 예약 불가로 반환한다.

        Args:
            date (str): 조회할 날짜 (예: '2026-05-20').
            hour_slots (List[str]): 1시간 단위 시간 슬롯 배열 (예: ['14:00', '15:00']).
            target_rooms (List[RoomDetail]): 조회 대상 방 리스트.

        Returns:
            List[RoomResult]: 방별 RoomAvailability 또는 에러 Exception 객체 배열.
        """
        # 1. 오늘 날짜와 목표 날짜를 date 객체로 변환
        today = datetime.now().date()
        target_date = datetime.strptime(date, '%Y-%m-%d').date()

        # 2. 오늘로부터 84일 이후인지 확인
        if (target_date - today).days >= self.RESERVATION_LIMIT_DAYS:
            # Rationale:
            #   그루브합주실 예약 폼이 최대 84일 이내 날짜만 지원함.
            #   초과 날짜는 예약 시스템 자체가 해당 날짜를 지원하지 않으므로 예약 불가(False)로 처리.
            return [
                RoomAvailability(
                    room_detail=room,
                    available=False,
                    available_slots={hour_str: False for hour_str in hour_slots},
                )
                for room in target_rooms
            ]

        # 3. 날짜가 유효한 범위 내에 있으면 데이터 가져오기 진행
        sem = self._prefetch_semaphore if prefetch else self._semaphore
        try:
            async with sem:
                html = await self._login_and_fetch_html(date, branch_gubun="sadang")
            soup = BeautifulSoup(html, "html.parser")
            tasks = [self._fetch_room_availability(room, hour_slots, soup) for room in target_rooms]
            results = await asyncio.gather(*tasks)
            return results
        except Exception as e:
            # 로그인 실패 전체 에러 핸들링을 원한다면 여기서 처리 가능하지만, 
            # 개별 room 에러가 아니라 전체 에러이므로 리스트로 변환해서 리턴하거나 
            # 상위로 예외를 던질 수 있음. 여기서는 예외 전파.
            return [e] * len(target_rooms)

    def _check_hour_slot(self, soup: BeautifulSoup, biz_item_id: str, hour_str: str) -> bool:
        """HTML 셀렉터로 특정 슬롯의 예약 가능 여부를 판별한다."""
        hour_int = int(hour_str.split(":")[0])
        selector = f'#reserve_time_{biz_item_id}_{hour_int}.reserve_time_off'
        elem = soup.select_one(selector)
        return bool(elem)

    async def _fetch_reserve_html(self, client: httpx.AsyncClient, date: str, branch_gubun: str):
        """지정 날짜·지점의 예약 페이지 HTML을 POST로 가져온다."""
        return await client.post(
            GROOVE_RESERVE_URL,
            data={"reserve_date": date, "gubun": branch_gubun},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": GROOVE_RESERVE_URL1
            }
        )

    async def _login_and_fetch_html(self, date: str, branch_gubun: str="sadang"):
        """로그인 세션을 확보한 뒤 예약 페이지 HTML 텍스트를 반환한다."""
        try:
            async with httpx.AsyncClient() as client:
                await LoginManager.login(client)
                resp = await self._fetch_reserve_html(client, date, branch_gubun)
            return resp.text
        except (GrooveCredentialError, GrooveLoginError):
            # 특정 로그인/자격증명 예외를 다시 발생시켜 호출자가 처리하도록 함
            raise

    async def _fetch_room_availability(
            self, room: RoomDetail, hour_slots: List[str], soup: BeautifulSoup
    ) -> RoomAvailability:
        """파싱된 HTML에서 단일 방의 시간대별 예약 가능 여부를 집계한다."""
        rm_ix = room.biz_item_id

        slots = {hour_str: self._check_hour_slot(soup, rm_ix, hour_str) for hour_str in hour_slots}
        
        overall = self.resolve_tri_state(slots)

        return RoomAvailability(
            room_detail=room,
            available=overall,
            available_slots=slots,
        )

# Register the crawler
registry.register("groove", GrooveCrawler())

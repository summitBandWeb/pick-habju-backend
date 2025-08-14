from typing import List, Union
from bs4 import BeautifulSoup
import httpx
from app.core.config import GROOVE_RESERVE_URL, GROOVE_RESERVE_URL1
from app.exception.crawler.groove_exception import (
    GrooveCredentialError,
    GrooveLoginError,
    GrooveRequestError,
    GrooveRoomParseError,
)
from app.utils.login import LoginManager
from app.models.dto import RoomAvailability, RoomKey
import asyncio
from datetime import datetime

# 결과 타입을 명확히 하기 위해 Union 사용
RoomResult = Union[RoomAvailability, Exception]

# --- 개별 슬롯(off/on) 체크 함수 ---
def check_hour_slot(soup: BeautifulSoup, biz_item_id: str, hour_str: str) -> bool:
    hour_int = int(hour_str.split(":")[0])
    selector = f'#reserve_time_{biz_item_id}_{hour_int}.reserve_time_off'
    elem = soup.select_one(selector)
    # 'off' 클래스가 있으면 예약 불가(False), 없으면 예약 가능(True)
    return not bool(elem)

# --- 예약정보 조회 함수 (네트워크 예외 처리 추가) ---
async def fetch_reserve_html(client: httpx.AsyncClient, date: str, branch_gubun: str):
    try:
        response = await client.post(
            GROOVE_RESERVE_URL,
            data={"reserve_date": date, "gubun": branch_gubun},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": GROOVE_RESERVE_URL1
            },
            timeout=10.0 # 타임아웃 설정
        )
        response.raise_for_status() # 2xx 이외의 상태 코드에 대해 예외 발생
        return response.text
    except httpx.RequestError as e:
        raise GrooveRequestError(f"네트워크 오류 발생: {e.request.url}")
    except httpx.HTTPStatusError as e:
        raise GrooveRequestError(f"HTTP 오류 발생: {e.response.status_code} - {e.request.url}")


# --- 로그인 및 HTML fetch를 try~except로 감싸는 함수 ---
async def login_and_fetch_html(date: str, branch_gubun: str="sadang"):
    try:
        async with httpx.AsyncClient() as client:
            await LoginManager.login(client)
            return await fetch_reserve_html(client, date, branch_gubun)
    except (GrooveCredentialError, GrooveLoginError, GrooveRequestError):
        # 발생한 예외를 그대로 다시 발생시켜 상위 호출자가 처리하도록 함
        raise

# --- 방의 예약가능 상태 확인 함수 (파싱 예외 처리 추가) ---
async def fetch_room_availability(
        room: RoomKey, hour_slots: List[str], soup: BeautifulSoup
) -> RoomAvailability:
    rm_ix = room.biz_item_id

    # 해당 방의 전체 예약 섹션이 존재하는지 먼저 확인
    reserve_section = soup.select_one(f"#reserve_section_{rm_ix}")
    if not reserve_section:
        raise GrooveRoomParseError(f"[{room.name}] 방의 HTML 구조를 찾을 수 없습니다.")

    slots = {hour_str: check_hour_slot(soup, rm_ix, hour_str) for hour_str in hour_slots}
    overall = all(slots.values())

    return RoomAvailability(
        name=room.name,
        branch=room.branch,
        business_id=room.business_id,
        biz_item_id=room.biz_item_id,
        available=overall,
        available_slots=slots,
    )

# --- 메인 함수 (개별 방 조회 실패 처리 로직 추가) ---
async def get_groove_availability(
    date: str,
    hour_slots: List[str],
    rooms: List[RoomKey]
) -> List[RoomResult]:

    today = datetime.now().date()
    target_date = datetime.strptime(date, '%Y-%m-%d').date()

    if (target_date - today).days >= 84:
        return [
            RoomAvailability(
                name=room.name,
                branch=room.branch,
                business_id=room.business_id,
                biz_item_id=room.biz_item_id,
                available="unknown",
                available_slots={hour_str: "unknown" for hour_str in hour_slots},
            ) for room in rooms
        ]

    html = await login_and_fetch_html(date, branch_gubun="sadang")
    soup = BeautifulSoup(html, "html.parser")

    # 개별 방 조회 실패 시 전체가 중단되지 않도록 safe_fetch 래퍼 함수 사용
    async def safe_fetch(room: RoomKey) -> RoomResult:
        try:
            return await fetch_room_availability(room, hour_slots, soup)
        except GrooveRoomParseError as e:
            # 파싱 실패 시, 성공 결과 대신 예외 객체를 반환
            print(f"개별 방 조회 실패: {e}") # 에러 로깅
            return e

    tasks = [safe_fetch(room) for room in rooms]
    results = await asyncio.gather(*tasks)
    return results

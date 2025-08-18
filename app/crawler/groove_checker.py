from typing import List
from bs4 import BeautifulSoup
import httpx
from app.core.config import GROOVE_RESERVE_URL, GROOVE_RESERVE_URL1
from app.exception.crawler.groove_exception import GrooveCredentialError, GrooveLoginError
from app.utils.login import LoginManager
from app.models.dto import RoomAvailability, RoomKey
import asyncio
from datetime import datetime

# --- 개별 슬롯(off/on) 체크 함수 ---
def check_hour_slot(soup: BeautifulSoup, biz_item_id: str, hour_str: str) -> bool:
    hour_int = int(hour_str.split(":")[0])
    selector = f'#reserve_time_{biz_item_id}_{hour_int}.reserve_time_off'
    elem = soup.select_one(selector)
    return bool(elem)

# --- 예약정보 조회 함수 ---
async def fetch_reserve_html(client: httpx.AsyncClient, date: str, branch_gubun: str):
    return await client.post(
        GROOVE_RESERVE_URL,
        data={"reserve_date": date, "gubun": branch_gubun},
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": GROOVE_RESERVE_URL1
        }
    )

# --- 로그인 및 HTML fetch를 try~except로 감싸는 함수 ---
async def login_and_fetch_html(date: str, branch_gubun: str="sadang"):
    try:
        async with httpx.AsyncClient() as client:
            await LoginManager.login(client)
            resp = await fetch_reserve_html(client, date, branch_gubun)
        return resp.text
    except (GrooveCredentialError, GrooveLoginError):
        # 특정 로그인/자격증명 예외를 다시 발생시켜 호출자가 처리하도록 함
        raise

# --- 방의 예약가능 상태 확인 함수 ---
async def fetch_room_availability(
        room: RoomKey, hour_slots: List[str], soup: BeautifulSoup
) -> RoomAvailability:
    rm_ix = room.biz_item_id

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

# --- 메인 함수 ---
async def get_groove_availability(
    date: str,
    hour_slots: List[str],
    rooms: List[RoomKey]
) -> List[RoomAvailability]:
    # --- 제거됨: 입력값 검증은 이제 메인 라우터에서 처리됩니다 ---

    # 1. 오늘 날짜와 목표 날짜를 date 객체로 변환
    today = datetime.now().date()
    target_date = datetime.strptime(date, '%Y-%m-%d').date()

    # 2. 오늘로부터 84일 이후인지 확인
    if (target_date - today).days >= 84:
        # 즉시 'unknown' 결과를 반환
        unknown_results = []
        for room in rooms:
            slots = {hour_str: "unknown" for hour_str in hour_slots}
            result = RoomAvailability(
                name=room.name,
                branch=room.branch,
                business_id=room.business_id,
                biz_item_id=room.biz_item_id,
                available="unknown",
                available_slots=slots,
            )
            unknown_results.append(result)
        return unknown_results

    # 3. 날짜가 유효한 범위 내에 있으면 데이터 가져오기 진행
    html = await login_and_fetch_html(date, branch_gubun="sadang")
    soup = BeautifulSoup(html, "html.parser")
    tasks = [fetch_room_availability(room, hour_slots, soup) for room in rooms]
    results = await asyncio.gather(*tasks)
    return results

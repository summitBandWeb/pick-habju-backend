from typing import List
from bs4 import BeautifulSoup
import httpx
from app.core.config import GROOVE_RESERVE_URL, GROOVE_RESERVE_URL1
from app.exception.crawler.groove_exception import GrooveCredentialError, GrooveLoginError
from app.utils.login import LoginManager
from app.models.dto import RoomAvailability, RoomKey
import asyncio
from datetime import datetime
from app.utils.client_loader import load_client

# --- 개별 슬롯(off/on) 체크 함수 ---
def check_hour_slot(soup: BeautifulSoup, biz_item_id: str, hour_str: str) -> bool:
    hour_int = int(hour_str.split(":")[0])
    selector = f'#reserve_time_{biz_item_id}_{hour_int}.reserve_time_off'
    elem = soup.select_one(selector)
    return bool(elem)

# --- 예약정보 조회 함수 ---
async def fetch_reserve_html(client: httpx.AsyncClient, date: str, branch_gubun: str):
    return await load_client(
        client,
        "POST",
        GROOVE_RESERVE_URL,
        data={"reserve_date": date, "gubun": branch_gubun},
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": GROOVE_RESERVE_URL1,
        },
    )

# --- 로그인 및 HTML fetch를 try~except로 감싸는 함수 ---
async def login_and_fetch_html(client: httpx.AsyncClient, date: str, branch_gubun: str="sadang"):
    try:
        # 외부에서 주입받은 client 재사용
        await LoginManager.login(client)  # 내부도 반드시 주입 client 사용하도록 구현되어야 함
        resp = await fetch_reserve_html(client, date, branch_gubun)
        return resp.text
    except (GrooveCredentialError, GrooveLoginError):
        # 로그인/자격증명 관련 예외는 상위에서 처리
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
    client: httpx.AsyncClient,
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
    html = await login_and_fetch_html(client, date, branch_gubun="sadang")
    soup = BeautifulSoup(html, "html.parser")
    tasks = [fetch_room_availability(room, hour_slots, soup) for room in rooms]
    results = await asyncio.gather(*tasks)
    return results

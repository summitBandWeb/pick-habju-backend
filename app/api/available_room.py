from fastapi import APIRouter
from typing import Union, List
import asyncio

from app.validate.common import validate_availability_request
from app.utils.room_router import filter_rooms_by_type
from app.models.dto import AvailabilityRequest, AvailabilityResponse, RoomAvailability

from app.crawler.dream_checker import get_dream_availability
from app.crawler.naver_checker import get_naver_availability
from app.crawler.groove_checker import get_groove_availability

router = APIRouter(prefix="/api/rooms/availability")

@router.post("/", response_model=AvailabilityResponse)
async def get_all_availability(request: AvailabilityRequest):
    # 1. 유효성 검증 (BaseCustomException은 전역 처리기가 처리)
    validate_availability_request(request.date, request.hour_slots, request.rooms)

    # 2. 타입별로 룸 필터링
    dream_rooms = filter_rooms_by_type(request.rooms, "dream")
    groove_rooms = filter_rooms_by_type(request.rooms, "groove")
    naver_rooms = filter_rooms_by_type(request.rooms, "naver")

    # 3. 각 타입에 대한 크롤러를 동시에 실행
    tasks = []
    if dream_rooms:
        tasks.append(get_dream_availability(request.date, request.hour_slots, dream_rooms))
    if groove_rooms:
        tasks.append(get_groove_availability(request.date, request.hour_slots, groove_rooms))
    if naver_rooms:
        tasks.append(get_naver_availability(request.date, request.hour_slots, naver_rooms))

    results_of_lists = await asyncio.gather(*tasks)

    # 4. 결과 통합
    all_results = [item for sublist in results_of_lists for item in sublist]

    # 5. 최종 성공 응답 준비 (None 값을 필터링하여 유효한 결과만 포함)
    successful_results = [r for r in all_results if r is not None]

    return AvailabilityResponse(
        date=request.date,
        hour_slots=request.hour_slots,
        results=successful_results,
        available_biz_item_ids=[r.biz_item_id for r in successful_results if r.available is True]
    )

from fastapi import APIRouter
from typing import Union, List

from utils.room_router import filter_rooms_by_type
from models.dto import AvailabilityRequest, AvailabilityResponse, RoomAvailability

from service.dream_checker import get_dream_availability
from service.naver_checker import get_naver_availability
from service.groove_checker import get_groove_availability

router = APIRouter(prefix="/api/rooms/availability")
RoomResult = Union[RoomAvailability, Exception]

@router.post("/")
async def your_handler(request: AvailabilityRequest):
    dream_rooms = filter_rooms_by_type(request.rooms, "dream")
    groove_rooms = filter_rooms_by_type(request.rooms, "groove")
    naver_rooms = filter_rooms_by_type(request.rooms, "naver")

    # 각 크롤러 실행 (모두 RoomResult 반환)
    dream_result: List[RoomResult] = await get_dream_availability(request.date, request.hour_slots, dream_rooms)
    groove_result: List[RoomResult] = await get_groove_availability(request.date, request.hour_slots, groove_rooms)
    naver_result: List[RoomResult] = await get_naver_availability(request.date, request.hour_slots, naver_rooms)

    all_results: List[RoomResult] = dream_result + groove_result + naver_result

    # 예외만 필터링해서 로그 남기기 (선택사항)
    for result in all_results:
        if isinstance(result, Exception):
            print(f"예약 실패: {type(result).__name__} - {result}")

    # 정상 결과만 AvailabilityResponse에 사용
    available_results: List[RoomAvailability] = [r for r in all_results if isinstance(r, RoomAvailability)]

    return AvailabilityResponse(
        date=request.date,
        hour_slots=request.hour_slots,
        results=available_results,
        available_biz_item_ids=[r.biz_item_id for r in available_results if r.available]
    )

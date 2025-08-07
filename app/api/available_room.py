# app/api/rooms.py
from fastapi import APIRouter, HTTPException
from typing import Union, List

from app.validate.common_validator import validate_availability_request
from app.utils.room_router import filter_rooms_by_type
from app.models.dto import AvailabilityRequest, AvailabilityResponse, RoomAvailability

from app.crawler.dream_checker import get_dream_availability
from app.crawler.naver_checker import get_naver_availability
from app.crawler.groove_checker import get_groove_availability

router = APIRouter(prefix="/api/rooms/availability")
RoomResult = Union[RoomAvailability, Exception]

@router.post("/", response_model=AvailabilityResponse)
async def your_handler(request: AvailabilityRequest):
    # 1) 공통 입력 검증
    try:
        validate_availability_request(request.date, request.hour_slots, request.rooms)
    except Exception as e:
        # 원하는 예외 타입/메시지로 변경
        raise HTTPException(status_code=400, detail=str(e))

    # 2) 타입별 룸 분리
    dream_rooms = filter_rooms_by_type(request.rooms, "dream")
    groove_rooms = filter_rooms_by_type(request.rooms, "groove")
    naver_rooms = filter_rooms_by_type(request.rooms, "naver")

    # 3) 크롤러 실행 (내부 검증 제거)
    dream_result: List[RoomResult] = await get_dream_availability(request.date, request.hour_slots, dream_rooms)
    groove_result: List[RoomResult] = await get_groove_availability(request.date, request.hour_slots, groove_rooms)
    naver_result: List[RoomResult] = await get_naver_availability(request.date, request.hour_slots, naver_rooms)

    # 4) 결과 통합 및 예외 로깅
    all_results: List[RoomResult] = dream_result + groove_result + naver_result
    for result in all_results:
        if isinstance(result, Exception):
            print(f"예약 실패: {type(result).__name__} - {result}")

    # 5) 정상 결과만 응답에 포함
    available_results = [r for r in all_results if isinstance(r, RoomAvailability)]
    return AvailabilityResponse(
        date=request.date,
        hour_slots=request.hour_slots,
        results=available_results,
        available_biz_item_ids=[r.biz_item_id for r in available_results if r.available]
    )

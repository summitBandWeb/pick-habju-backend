from fastapi import APIRouter, HTTPException
from typing import Union, List

from app.validate.common import validate_availability_request
from app.utils.room_router import filter_rooms_by_type
from app.models.dto import AvailabilityRequest, AvailabilityResponse, RoomAvailability

from app.crawler.dream_checker import get_dream_availability
from app.crawler.naver_checker import get_naver_availability
from app.crawler.groove_checker import get_groove_availability

router = APIRouter(prefix="/api/rooms/availability")
RoomResult = Union[RoomAvailability, Exception]


@router.post("/", response_model=AvailabilityResponse)
async def get_all_availability(request: AvailabilityRequest):
    # 1. 중앙화된 입력값 검증
    try:
        validate_availability_request(request.date, request.hour_slots, request.rooms)
    except Exception as e:
        # 더 세분화된 오류 메시지를 위해 특정 유효성 검사 예외를 잡을 수 있음
        raise HTTPException(status_code=400, detail=f"잘못된 입력값: {e}")

    # 2. 타입별로 룸 필터링 (dream, groove, naver)
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

    # 이제 크롤러는 자체적으로 유효성 검사를 수행하지 않음.
    import asyncio
    results_of_lists = await asyncio.gather(*tasks)

    # 4. 리스트의 리스트를 단일 리스트로 만들고 예외를 로깅
    all_results: List[RoomResult] = [item for sublist in results_of_lists for item in sublist]

    for result in all_results:
        if isinstance(result, Exception):
            # 실제 애플리케이션에서는 적절한 로깅을 사용해야 함 (예: structlog, logging 모듈)
            print(f"크롤러 오류: {type(result).__name__} - {result}")

    # 5. 예외를 필터링하고 최종 성공 응답을 준비
    successful_results = [r for r in all_results if isinstance(r, RoomAvailability)]

    return AvailabilityResponse(
        date=request.date,
        hour_slots=request.hour_slots,
        results=successful_results,
        available_biz_item_ids=[r.biz_item_id for r in successful_results if r.available is True]
    )

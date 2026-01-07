from fastapi import APIRouter
from typing import Union, List
import asyncio
import logging
from app.exception.base_exception import BaseCustomException

from app.validate.request_validator import validate_availability_request
from app.utils.room_router import filter_rooms_by_type
from app.models.dto import AvailabilityRequest, AvailabilityResponse, RoomAvailability

from app.crawler.registry import CRAWLER_REGISTRY

router = APIRouter(prefix="/api/rooms/availability")
logger = logging.getLogger("app")

@router.post("/", response_model=AvailabilityResponse)
@router.post("", response_model=AvailabilityResponse)
async def your_handler(request: AvailabilityRequest):
    # 1) 공통 입력 검증 - 커스텀 예외는 전역 핸들러가 처리
    validate_availability_request(request.date, request.hour_slots, request.rooms)

    # 2. 레지스트리에 등록된 크롤러들을 자동으로 실행
    tasks = []
    for room_type, crawler_func in CRAWLER_REGISTRY.items():
        target_rooms = filter_rooms_by_type(request.rooms, room_type)
        if target_rooms:
            tasks.append(crawler_func(request.date, request.hour_slots, target_rooms))

    results_of_lists = await asyncio.gather(*tasks)

    # 4. 결과 통합
    all_results = [item for sublist in results_of_lists for item in sublist]

    # 예외 결과 로깅(중앙 핸들러로 전달되지 않으므로 여기서 기록)
    errors = [e for e in all_results if isinstance(e, Exception)]
    for err in errors:
        if isinstance(err, BaseCustomException):
            logger.warning({
                "timestamp": request.date,  # 요청 맥락에서 대표 타임스탬프가 없다면 서버 시간으로 대체 가능
                "status": err.status_code,
                "errorCode": err.error_code,
                "message": err.message,
            })
        else:
            logger.error({
                "timestamp": request.date,
                "status": 500,
                "errorCode": "Common-001",
                "message": str(err),
            })

    # 5. 최종 성공 응답 준비 (None 값을 필터링하여 유효한 결과만 포함)
    # 예외 객체가 혼재할 수 있으므로 정상 결과만 선별
    successful_results = [r for r in all_results if r is not None and not isinstance(r, Exception)]

    return AvailabilityResponse(
        date=request.date,
        hour_slots=request.hour_slots,
        results=successful_results,
        available_biz_item_ids=[r.biz_item_id for r in successful_results if r.available is True]
    )

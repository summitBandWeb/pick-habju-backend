from fastapi import APIRouter, Depends
from typing import Union, List
import asyncio
import logging
from app.exception.base_exception import BaseCustomException

from app.validate.request_validator import validate_availability_request
from app.utils.room_router import filter_rooms_by_type
from app.models.dto import AvailabilityRequest, AvailabilityResponse, RoomAvailability
from app.exception.base_exception import BaseCustomException

from app.crawler.base import BaseCrawler
from app.api.dependencies import get_crawlers_map

router = APIRouter(prefix="/api/rooms/availability")
logger = logging.getLogger("app")

@router.post("/", response_model=AvailabilityResponse)
@router.post("", response_model=AvailabilityResponse)
async def your_handler(
    request: AvailabilityRequest,
    crawlers_map: dict = Depends(get_crawlers_map)
):
    # 1) 공통 입력 검증 - 커스텀 예외는 전역 핸들러가 처리
    validate_availability_request(request.date, request.hour_slots, request.rooms)

    # 2 & 3. 각 크롤러별로 room 필터링 및 조회를 동시에 실행
    tasks = []
    
    # Injected check: iterate over the injected map directly
    for crawler_type, crawler in crawlers_map.items():
        # 1. 해당 타입의 룸만 필터링
        target_rooms = filter_rooms_by_type(request.rooms, crawler_type)
        
        # 2. 해당 타입의 룸이 있다면 태스크 추가
        if target_rooms:
            # BaseCrawler의 check_availability 호출
            tasks.append(crawler.check_availability(request.date, request.hour_slots, target_rooms))

    results_of_lists = await asyncio.gather(*tasks)

    # 4. 결과 통합
    all_results = [item for sublist in results_of_lists for item in sublist]

    # 예외 결과 로깅(중앙 핸들러로 전달되지 않으므로 여기서 기록)
    errors = [e for e in all_results if isinstance(e, Exception)]
    for err in errors:
        if isinstance(err, BaseCustomException):
            logger.warning({
                "timestamp": request.date,
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
    successful_results = [r for r in all_results if r is not None and not isinstance(r, Exception)]

    return AvailabilityResponse(
        date=request.date,
        hour_slots=request.hour_slots,
        results=successful_results,
        available_biz_item_ids=[r.biz_item_id for r in successful_results if r.available is True]
    )

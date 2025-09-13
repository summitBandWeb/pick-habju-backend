from fastapi import APIRouter, Request
from typing import Union, List
import asyncio
import logging
from app.exception.base_exception import BaseCustomException

from app.validate.request_validator import validate_availability_request
from app.utils.room_router import filter_rooms_by_type
from app.models.dto import AvailabilityRequest, AvailabilityResponse, RoomAvailability
from app.exception.base_exception import BaseCustomException

from app.crawler.dream_checker import get_dream_availability
from app.crawler.naver_checker import get_naver_availability
from app.crawler.groove_checker import get_groove_availability

router = APIRouter(prefix="/api/rooms/availability")
logger = logging.getLogger("app")

AGGREGATE_TIMEOUT = 15.0

@router.post("/", response_model=AvailabilityResponse)
@router.post("", response_model=AvailabilityResponse)
async def your_handler(req: AvailabilityRequest, request: Request):
    # 1) 공통 입력 검증 - 커스텀 예외는 전역 핸들러가 처리
    validate_availability_request(req.date, req.hour_slots, req.rooms)

    # 2. 타입별로 룸 필터링
    dream_rooms = filter_rooms_by_type(req.rooms, "dream")
    groove_rooms = filter_rooms_by_type(req.rooms, "groove")
    naver_rooms = filter_rooms_by_type(req.rooms, "naver")

    client = request.app.state.http

    async def safe(coro):
        try:
            return await coro
        except Exception as e:
            return [e]

    tasks = []
    results_of_lists = []
    # 3. 각 타입에 대한 크롤러를 동시에 실행
    async with asyncio.timeout(AGGREGATE_TIMEOUT):
        async with asyncio.TaskGroup() as tg:
            if dream_rooms:
                tasks.append(tg.create_task(safe(get_dream_availability(client, req.date, req.hour_slots, dream_rooms))))
            if groove_rooms:
                tasks.append(tg.create_task(safe(get_groove_availability(client, req.date, req.hour_slots, groove_rooms))))
            if naver_rooms:
                tasks.append(tg.create_task(safe(get_naver_availability(client, req.date, req.hour_slots, naver_rooms))))

    for t in tasks:
        results_of_lists.append(t.result())

    # 4. 결과 통합
    all_results = [item for sublist in results_of_lists for item in sublist]

    # 예외 결과 로깅(중앙 핸들러로 전달되지 않으므로 여기서 기록)
    errors = [e for e in all_results if isinstance(e, Exception)]
    for err in errors:
        if isinstance(err, BaseCustomException):
            logger.warning({
                "timestamp": req.date,  # 요청 맥락에서 대표 타임스탬프가 없다면 서버 시간으로 대체 가능
                "status": err.status_code,
                "errorCode": err.error_code,
                "message": err.message,
            })
        else:
            logger.error({
                "timestamp": req.date,
                "status": 500,
                "errorCode": "Common-001",
                "message": str(err),
            })

    # 5. 최종 성공 응답 준비 (None 값을 필터링하여 유효한 결과만 포함)
    # 예외 객체가 혼재할 수 있으므로 정상 결과만 선별
    successful_results = [r for r in all_results if r is not None and not isinstance(r, Exception)]

    return AvailabilityResponse(
        date=req.date,
        hour_slots=req.hour_slots,
        results=successful_results,
        available_biz_item_ids=[r.biz_item_id for r in successful_results if r.available is True]
    )

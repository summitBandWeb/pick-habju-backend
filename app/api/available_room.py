from fastapi import APIRouter
from typing import Union, List

from app.utils.room_router import filter_rooms_by_type
from app.models.dto import AvailabilityRequest, AvailabilityResponse, RoomAvailability

from app.crawler.dream_checker import get_dream_availability
from app.crawler.naver_checker import get_naver_availability
from app.crawler.groove_checker import get_groove_availability

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi import limit, shared_limit

from app.exception.common.rate_limit_exception import OverRateLimitError

router = APIRouter(prefix="/api/rooms/availability")
RoomResult = Union[RoomAvailability, Exception]

limiter = Limiter(key_func=get_remote_address)

dream_limiter = limiter.shared_limit("250/minute", scope="dream")
groove_limiter = limiter.shared_limit("250/minute", scope="groove")
naver_limiter = limiter.shared_limit("600/minute", scope="naver")

@router.post("/")
@limiter.limit("1000/minute")  # 전체 엔드포인트 ratelimit도 병행 (optional)
async def your_handler(request: AvailabilityRequest):
    dream_rooms = filter_rooms_by_type(request.rooms, "dream")
    groove_rooms = filter_rooms_by_type(request.rooms, "groove")
    naver_rooms = filter_rooms_by_type(request.rooms, "naver")
    error_rooms = []
    error_occured = False
    try:
        if dream_rooms:
            await dream_limiter(request)
    except:
        error_rooms += "드림"
        error_occured = True
    try:    
        if groove_rooms:
            await groove_limiter(request)
    except:
        error_rooms += "그루브"
        error_occured = True
    try:    
        if naver_rooms:
            await naver_limiter(request)
    except:
        error_rooms += "네이버"
        error_occured = True
    if error_occured:
        room_str = ", ".join(error_rooms)
        raise OverRateLimitError(f"[{room_str}] rate limit 초과 오류")
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

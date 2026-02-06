from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional
from app.api.dependencies import get_availability_service
from app.models.dto import AvailabilityRequest, AvailabilityResponse
from app.core.response import ApiResponse
from app.services.availability_service import AvailabilityService
from app.core.limiter import limiter
from app.core.config import RATE_LIMIT_PER_MINUTE

router = APIRouter(prefix="/api/rooms/availability", tags=["예약 가능 여부"])

@router.get(
    "/",
    response_model=ApiResponse[AvailabilityResponse],
    summary="합주실 지도 기반 검색 (예약 가능 여부 포함)",
    description="""
지정된 날짜와 시간대에 대해 인원수에 맞는 합주실을 **지도 영역** 내에서 검색하고 예약 가능 여부를 확인합니다.
모든 검색은 지도 기반이므로 좌표 정보가 필수입니다.
""",
)
@router.get("", response_model=ApiResponse[AvailabilityResponse], include_in_schema=False)
@limiter.limit(f"{RATE_LIMIT_PER_MINUTE}/minute")  # Rate Limit 적용
async def check_room_availability(
    request: Request,
    date: str = Query(..., description="날짜 (YYYY-MM-DD)"),
    capacity: int = Query(..., description="사용 인원 수"),
    start_hour: str = Query(..., description="시작 시간 (HH:MM)"),
    end_hour: str = Query(..., description="종료 시간 (HH:MM)"),
    swLat: float = Query(..., description="남서쪽 위도 (필수)"),
    swLng: float = Query(..., description="남서쪽 경도 (필수)"),
    neLat: float = Query(..., description="북동쪽 위도 (필수)"),
    neLng: float = Query(..., description="북동쪽 경도 (필수)"),
    service: AvailabilityService = Depends(get_availability_service)
):

    """
    GET 요청을 받아 합주실 예약 가능 여부를 조회합니다.
    지도 영역 좌표(swLat, neLat 등)가 주어지면 해당 범위 내의 룸만 필터링하여 반환합니다.

    Args:
        date: 예약 날짜 (YYYY-MM-DD 형식)
        capacity: 사용 인원 수 (1 이상의 정수)
        start_hour: 시작 시간 (HH:MM 형식, 예: 14:00)
        end_hour: 종료 시간 (HH:MM 형식, 예: 16:00)
        swLat: 남서쪽 위도 (필수)
        swLng: 남서쪽 경도 (필수)
        neLat: 북동쪽 위도 (필수)
        neLng: 북동쪽 경도 (필수)

    Returns:
        ApiResponse[AvailabilityResponse]: 예약 가능 여부 및 상세 정보 (branch_summary 포함)

    Raises:
        HTTPException: 유효하지 않은 파라미터 시 400 에러
    """
    
    svc_request = AvailabilityRequest(
        date = date,
        capacity = capacity,
        start_hour = start_hour,
        end_hour = end_hour,
        swLat = swLat,
        swLng = swLng,
        neLat = neLat,
        neLng = neLng
    )

    result = await service.check_availability(request=svc_request)
    return ApiResponse.success(result=result)
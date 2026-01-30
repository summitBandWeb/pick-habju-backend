from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.dependencies import get_availability_service
from app.models.dto import AvailabilityRequest, AvailabilityResponse
from app.core.response import ApiResponse
from app.services.availability_service import AvailabilityService

router = APIRouter(prefix="/api/rooms/availability", tags=["예약 가능 여부"])


@router.get(
    "/",
    response_model=ApiResponse[AvailabilityResponse],
    summary="합주실 예약 가능 여부 조회",
    description="지정된 날짜와 시간대에 대해 인원수에 맞는 합주실 룸들의 예약 가능 여부를 확인합니다.",
)
@router.get("", response_model=ApiResponse[AvailabilityResponse], include_in_schema=False)
async def check_room_availability(
    date: str = Query(..., description="날짜 (YYYY-MM-DD)"),
    capacity: int = Query(..., description="사용 인원 수"),
    start_hour: str = Query(..., description="시작 시간 (HH:MM)"),
    end_hour: str = Query(..., description="종료 시간 (HH:MM)"),
    service: AvailabilityService = Depends(get_availability_service)
):
    """
    GET 요청을 받아 합주실 예약 가능 여부를 조회합니다.

    Args:
        date: 예약 날짜 (YYYY-MM-DD 형식)
        capacity: 사용 인원 수 (1 이상의 정수)
        start_hour: 시작 시간 (HH:MM 형식, 예: 14:00)
        end_hour: 종료 시간 (HH:MM 형식, 예: 16:00)

    Returns:
        ApiResponse[AvailabilityResponse]: 예약 가능 여부 및 상세 정보

    Raises:
        HTTPException: 유효하지 않은 파라미터 시 400 에러
    """
    
    svc_request = AvailabilityRequest(
        date = date,
        capacity = capacity,
        start_hour = start_hour,
        end_hour = end_hour
    )

    result = await service.check_availability(request=svc_request)
    return ApiResponse.success(result=result)
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.dependencies import get_availability_service
from app.models.dto import AvailabilityRequest, AvailabilityResponse
from app.services.availability_service import AvailabilityService


router = APIRouter(prefix="/api/rooms/availability")



@router.get("/", response_model=AvailabilityResponse)
@router.get("", response_model=AvailabilityResponse)
async def check_room_availability(
    date: str = Query(..., description="날짜 (YYYY-MM-DD)"),
    capacity: int = Query(..., description="사용 인원 수"),
    start_hour: str = Query(..., description="시작 시간 (HH:MM)"),
    end_hour: str = Query(..., description="종료 시간 (HH:MM)"),
    service: AvailabilityService = Depends(get_availability_service)
):
    """
    GET 요청을 받아 내부적으로 필요한 데이터 형식으로 변환 후 
    Service 레이어에 비즈니스 로직을 위임합니다.
    """
    
    svc_request = AvailabilityRequest(
        date = date,
        capacity = capacity,
        start_hour = start_hour,
        end_hour = end_hour
    )

    return await service.check_availability(request= svc_request)
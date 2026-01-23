from fastapi import APIRouter, Depends
from app.api.dependencies import get_availability_service
from app.models.dto import AvailabilityRequest, AvailabilityResponse
from app.services.availability_service import AvailabilityService

router = APIRouter(prefix="/api/rooms/availability", tags=["예약 가능 여부"])


@router.post(
    "/",
    response_model=AvailabilityResponse,
    summary="합주실 예약 가능 여부 조회",
    description="""
지정된 날짜와 시간 슬롯에 대해 합주실 룸들의 예약 가능 여부를 확인합니다.

### 요청 예시
```json
{
    "date": "2025-07-03",
    "hour_slots": ["15:00", "16:00"],
    "rooms": [
        {
            "name": "블랙룸",
            "branch": "비쥬 합주실 1호점",
            "business_id": "522011",
            "biz_item_id": "3968885"
        }
    ]
}
```
    """,
)
@router.post("", response_model=AvailabilityResponse, include_in_schema=False)
async def check_room_availability(
    request: AvailabilityRequest,
    service: AvailabilityService = Depends(get_availability_service)
):
    """
    Check availability for requested rooms.
    Business logic is delegated to AvailabilityService.
    """
    return await service.check_availability(request)

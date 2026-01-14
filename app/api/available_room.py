from fastapi import APIRouter, Depends
from app.api.dependencies import get_availability_service
from app.models.dto import AvailabilityRequest, AvailabilityResponse
from app.services.availability_service import AvailabilityService

router = APIRouter(prefix="/api/rooms/availability")


@router.post("/", response_model=AvailabilityResponse)
@router.post("", response_model=AvailabilityResponse)
async def check_room_availability(
    request: AvailabilityRequest,
    service: AvailabilityService = Depends(get_availability_service)
):
    """
    Check availability for requested rooms.
    Business logic is delegated to AvailabilityService.
    """
    return await service.check_availability(request)

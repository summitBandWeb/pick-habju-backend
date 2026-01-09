from fastapi import APIRouter, Depends
from typing import Dict
import logging
from app.api.dependencies import get_crawlers_map
from app.crawler.base import BaseCrawler
from app.models.dto import AvailabilityRequest, AvailabilityResponse
from app.services.availability_service import AvailabilityService

router = APIRouter(prefix="/api/rooms/availability")
logger = logging.getLogger("app")

# Dependency for Service
def get_availability_service(
    crawlers_map: Dict[str, BaseCrawler] = Depends(get_crawlers_map)
) -> AvailabilityService:
    return AvailabilityService(crawlers_map)

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

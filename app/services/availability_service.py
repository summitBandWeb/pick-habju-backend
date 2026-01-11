from typing import List, Dict, Union
import asyncio
import logging
from app.models.dto import AvailabilityRequest, AvailabilityResponse, RoomAvailability, RoomKey
from app.validate.request_validator import validate_availability_request
from app.utils.room_router import filter_rooms_by_type
from app.crawler.base import BaseCrawler
from app.exception.base_exception import BaseCustomException

logger = logging.getLogger("app")

class AvailabilityService:
    def __init__(self, crawlers_map: Dict[str, BaseCrawler]):
        self.crawlers_map = crawlers_map

    async def check_availability(self, request: AvailabilityRequest) -> AvailabilityResponse:
    async def check_availability(self, request: AvailabilityRequest) -> AvailabilityResponse:
        validate_availability_request(request.date, request.hour_slots, request.rooms)

        # Prepare tasks for each crawler
        tasks = []
        for crawler_type, crawler in self.crawlers_map.items():
            target_rooms = filter_rooms_by_type(request.rooms, crawler_type)
            if target_rooms:
                tasks.append(crawler.check_availability(request.date, request.hour_slots, target_rooms))

        if not tasks:
            return AvailabilityResponse(
                date=request.date,
                hour_slots=request.hour_slots,
                results=[],
                available_biz_item_ids=[]
            )

        results_of_lists = await asyncio.gather(*tasks)
        all_results = [item for sublist in results_of_lists for item in sublist]

        self._log_errors(all_results, request.date)

        successful_results = [r for r in all_results if r is not None and not isinstance(r, Exception)]

        return AvailabilityResponse(
            date=request.date,
            hour_slots=request.hour_slots,
            results=successful_results,
            available_biz_item_ids=[r.biz_item_id for r in successful_results if r.available is True]
        )

    def _log_errors(self, results: List[Union[RoomAvailability, Exception]], date_context: str):
        errors = [e for e in results if isinstance(e, Exception)]
        for err in errors:
            if isinstance(err, BaseCustomException):
                logger.warning({
                    "timestamp": date_context,
                    "status": err.status_code,
                    "errorCode": err.error_code,
                    "message": err.message,
                })
            else:
                logger.error({
                    "timestamp": date_context,
                    "status": 500,
                    "errorCode": "Common-001",
                    "message": str(err),
                })

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from utils.room_router import filter_rooms_by_type
from models.dto import AvailabilityRequest, AvailabilityResponse

#from service.dream_checker import get_dream_availability
from service.naver_checker import get_naver_availability
from service.groove_checker import get_groove_availability

router = APIRouter(prefix="/api/available")

@router.post("/")
async def your_handler(request: AvailabilityRequest):
    dream_rooms = filter_rooms_by_type(request.rooms, "dream")
    groove_rooms = filter_rooms_by_type(request.rooms, "groove")
    naver_rooms = filter_rooms_by_type(request.rooms, "naver")

    # 각 크롤러에 바로 전달
    #dream_result= await get_dream_availability(request.date, request.hour_slots, dream_rooms)
    groove_result= await get_groove_availability(request.date, request.hour_slots, groove_rooms)
    naver_result = await get_naver_availability(request.date, request.hour_slots, naver_rooms)

    # 응답 구성
    results = groove_result + naver_result # + dream_result
    return AvailabilityResponse(
        date=request.date,
        hour_slots=request.hour_slots,
        results=results,
        available_biz_item_ids=[r.biz_item_id for r in results if r.available]
    )

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from service.groove_checker import get_groove_availability
from service.dream_checker import get_dream_availability
from service.naver_checker import get_naver_availability

router = APIRouter(prefix="/api/available")

class AvailabilityRequest(BaseModel):
    date: str
    hour_slots: List[str]

@router.post("/")
async def check_availability(req: AvailabilityRequest):
    groove_result = await get_groove_availability(req.date, req.hour_slots)
    naver_result = await get_naver_availability(req.date, req.hour_slots)
    dream_result = await get_dream_availability(req.date, req.hour_slots)

    return groove_result + naver_result + dream_result

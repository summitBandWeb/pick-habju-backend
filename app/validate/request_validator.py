from typing import List
from fastapi import HTTPException
from app.models.dto import RoomDetail
from app.validate.date_validator import validate_date
from app.validate.hour_validator import validate_hour_slots
from app.validate.room_detail_validator import validate_room_detail_list

def validate_availability_request(
        date: str,
        hour_slots: List[str],
        target_rooms: List[RoomDetail],
):
    """
    요청의 유효성을 검사합니다.
    • 날짜 포맷 및 유효성 검증
    • 시간 슬롯 포맷 및 과거/연속성 검증
    • room detail 리스트 및 개별 room detail 검증
    """
    validate_date(date)
    validate_hour_slots(hour_slots, date)

    # RoomKey 관련 모든 검증을 한 번에 처리
    validate_room_detail_list(target_rooms)

def validate_map_coordinates(swLat: float, swLng: float, neLat: float, neLng: float):
    """
    지도 좌표의 유효성을 검증합니다.
    """
    # 1. 위도 경도 범위 체크
    if not (-90 <= swLat <= 90) or not (-90 <= neLat <= 90):
        raise HTTPException(status_code=400, detail="위도는 -90도에서 90도 사이여야 합니다.")
    
    if not (-180 <= swLng <= 180) or not (-180 <= neLng <= 180):
        raise HTTPException(status_code=400, detail="경도는 -180도에서 180도 사이여야 합니다.")

    # 2. 영역 논리 체크 (SW < NE)
    if swLat >= neLat:
        raise HTTPException(status_code=400, detail="남서쪽 위도(swLat)는 북동쪽 위도(neLat)보다 작아야 합니다.")

    if swLng >= neLng:
        raise HTTPException(status_code=400, detail="남서쪽 경도(swLng)는 북동쪽 경도(neLng)보다 작아야 합니다.")

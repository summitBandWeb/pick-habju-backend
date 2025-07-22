from pydantic import BaseModel
from typing import List, Dict, Union

# 요청 DTO
class RoomKey(BaseModel):
    name: str # 합주실 룸 이름(블랙룸)
    branch: str # 합주실 지점 이름(비쥬합주실 1호점)
    business_id: str # 합주실 지점 id
    biz_item_id: str # 합주실 룸 id

class AvailabilityRequest(BaseModel):
    date: str # 예약 날짜 (2025-07-03)
    hour_slots: List[str] # 확인할 시간슬롯들 (15~17시면 ["15:00", "16:00"])
    rooms: List[RoomKey] # 합주실 룸 정보들

# 응답 DTO (단일 방 기준 상세 정보)
class RoomAvailability(BaseModel):
    name: str # 합주실 룸 이름(블랙룸)
    branch: str # 합주실 지점 이름(비쥬합주실 1호점)
    business_id: str # 합주실 지점 id
    biz_item_id: str # 합주실 룸 id
    available: Union[bool, str] # 합주실 최종 예약 가능 여부
    available_slots: Dict[str, Union[bool, str]] # 합주실 예약 가능한 시간슬롯들("16:00": true,"17:00": false)

# 응답 전체 DTO (요약 필드 포함)
class AvailabilityResponse(BaseModel):
    date: str 
    hour_slots: List[str] 
    results: List[RoomAvailability] # 합주실 룸 정보들
    available_biz_item_ids: List[str] # 예약 가능한 합주실 룸 id들(프론트개발편리성을 위한)
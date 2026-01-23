from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Union

# 합주실 정보 DTO
class RoomDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    # alias="DB에서_오는_키_이름"
    name: str = Field(alias="room_name")          # room_name -> name
    branch: str = Field(alias="branch_name")      # branch_name -> branch
    business_id: str = Field(alias="branch_id")   # branch_id -> business_id
    biz_item_id: str = Field(alias="room_id")     # room_id -> biz_item_id
    
    imageUrls: List[str] = Field(alias="image_urls") # image_urls -> imageUrls
    maxCapacity: int = Field(alias="max_capacity")
    recommendCapacity: int = Field(alias="recommend_capacity")
    pricePerHour: int = Field(alias="price_per_hour")
    canReserveOneHour: bool = Field(alias="can_reserve_one_hour")
    requiresCallOnSameDay: bool = Field(alias="requires_call_on_sameday")

# 요청 DTO
class AvailabilityRequest(BaseModel):
    date: str # 예약 날짜 (2025-07-03)
    capacity: int 
    start_hour: str
    end_hour: str

# 응답 DTO (단일 방 기준 상세 정보)
class RoomAvailability(BaseModel):
    room_detail: RoomDetail
    available: Union[bool, str] # 합주실 최종 예약 가능 여부
    available_slots: Dict[str, Union[bool, str]] # 합주실 예약 가능한 시간슬롯들("16:00": true,"17:00": false)

# 응답 전체 DTO (요약 필드 포함)
class AvailabilityResponse(BaseModel):
    date: str 
    hour_slots: List[str]
    results: List[RoomAvailability] # 합주실 룸 정보들
    available_biz_item_ids: List[str] # 예약 가능한 합주실 룸 id들(프론트 개발 편리성을 위한)

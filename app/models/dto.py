from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Dict, Union, Any, Optional

# 합주실 정보 DTO
class RoomDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    # DB 컬럼명과 일치하도록 alias 설정
    name: str                                       # DB: name
    branch: str                                     # DB: branch (join으로 {'name': ...} 객체)
    business_id: str                                # DB: business_id
    biz_item_id: str                                # DB: biz_item_id
    
    imageUrls: List[str] = Field(default_factory=list, alias="image_urls") # DB: image_urls (nullable)
    maxCapacity: int = Field(alias="max_capacity")   # DB: max_capacity
    recommendCapacity: int = Field(alias="recommend_capacity")
    pricePerHour: int = Field(alias="price_per_hour")
    canReserveOneHour: bool = Field(alias="can_reserve_one_hour")
    requiresCallOnSameDay: bool = Field(alias="requires_call_on_sameday")

    @field_validator('branch', mode='before')
    @classmethod
    def extract_branch_name(cls, v: Any) -> str:
        """Supabase join에서 {'name': 'branch_name'} 객체를 문자열로 변환"""
        if isinstance(v, dict):
            return v.get('name', '')
        return v

    @field_validator('imageUrls', mode='before')
    @classmethod
    def handle_null_image_urls(cls, v: Any) -> List[str]:
        """DB에서 null로 오는 image_urls를 빈 리스트로 변환"""
        if v is None:
            return []
        return v

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

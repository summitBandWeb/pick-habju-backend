from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Dict, Union, Any, Optional

# Room Information DTO (DB Query Result)
class RoomDetail(BaseModel):
    """Room detail information (DB column mapping with branch join)"""
    model_config = ConfigDict(populate_by_name=True)

    # DB 컬럼명과 일치 (room 테이블 + branch(name) join)
    name: str = Field(description="Rehearsal room name")
    branch: str = Field(description="Branch name (extracted from join)")
    business_id: str = Field(description="Naver Booking Business ID")
    biz_item_id: str = Field(description="Naver Booking Room ID")

    imageUrls: List[str] = Field(default_factory=list, alias="image_urls", description="List of room image URLs")
    maxCapacity: int = Field(alias="max_capacity", description="Maximum capacity")
    recommendCapacity: int = Field(alias="recommend_capacity", description="Recommended capacity")
    
    # 신규 필드 추가
    baseCapacity: Optional[int] = Field(None, alias="base_capacity", description="Base capacity for extra charge")
    extraCharge: Optional[int] = Field(None, alias="extra_charge", description="Extra charge per person")
    lat: Optional[float] = Field(None, description="Branch latitude")
    lng: Optional[float] = Field(None, description="Branch longitude")

    pricePerHour: int = Field(alias="price_per_hour", description="Price per hour (KRW)")
    canReserveOneHour: bool = Field(alias="can_reserve_one_hour", description="Whether 1-hour reservation is available")
    requiresCallOnSameDay: bool = Field(alias="requires_call_on_sameday", description="Whether same-day reservation requires a call")

    @field_validator('branch', mode='before')
    @classmethod
    def extract_branch_info(cls, v: Any) -> str:
        """Supabase join 결과 정제"""
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

# Request DTO
class AvailabilityRequest(BaseModel):
    """Request for checking availability"""
    date: str = Field(..., description="Reservation date (YYYY-MM-DD)")
    capacity: int = Field(..., description="Number of users")
    start_hour: str = Field(..., description="Start time (HH:MM)")
    end_hour: str = Field(..., description="End time (HH:MM)")
    
    # 지도 영역 좌표 (필수)
    swLat: float = Field(..., description="South-West Latitude")
    swLng: float = Field(..., description="South-West Longitude")
    neLat: float = Field(..., description="North-East Latitude")
    neLng: float = Field(..., description="North-East Longitude")


# Room Info (Response용 평탄화된 모델)
class RoomInfo(BaseModel):
    """조건에 맞는 개별 룸 정보"""
    name: str
    branch: str
    business_id: str
    biz_item_id: str
    imageUrls: List[str]
    maxCapacity: int
    recommendCapacity: int
    baseCapacity: Optional[int] = None
    extraCharge: Optional[int] = None
    pricePerHour: int
    canReserveOneHour: bool
    requiresCallOnSameDay: bool
    
# Crawler Result DTO (Internal Logic Use Only)
class RoomAvailability(BaseModel):
    """Availability information for a single room (Internal Use)"""
    room_detail: RoomDetail = Field(..., description="Room detail information")
    available: Union[bool, str] = Field(..., description="Availability status (true/false/unknown)")
    available_slots: Dict[str, Union[bool, str]] = Field(..., description="Availability by time slot")

# Branch Summary Stat Model
class BranchStats(BaseModel):
    """지점별 요약 정보"""
    min_price: int = Field(..., description="Minimum price in this branch")
    available_count: int = Field(..., description="Number of available rooms")
    lat: Optional[float] = Field(None, description="Branch latitude")
    lng: Optional[float] = Field(None, description="Branch longitude")

# Full Response DTO (Legacy + Map Extension)
class AvailabilityResponse(BaseModel):
    """Response for availability check
    
    기존 응답 구조를 유지하면서, 지도 검색을 위한 branch_summary를 추가했습니다.
    """
    date: str = Field(..., description="Checked date")
    start_hour: str = Field(..., description="Checked start time")
    end_hour: str = Field(..., description="Checked end time")
    
    # 기존 필드 유지
    hour_slots: List[str] = Field(default_factory=list, description="List of checked hour slots")
    available_biz_item_ids: List[str] = Field(default_factory=list, description="List of available biz_item_ids")
    results: List[RoomAvailability] = Field(..., description="List of rooms with availability info")
    
    # 지도 검색을 위한 신규 필드
    branch_summary: Dict[str, BranchStats] = Field(default_factory=dict, description="Summary stats per branch for map markers")



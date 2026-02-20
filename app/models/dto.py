from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Dict, Union, Any, Optional

# Room Information DTO (DB Query Result)
class RoomDetail(BaseModel):
    """Room detail information (DB column mapping with branch join)"""
    model_config = ConfigDict(populate_by_name=True)

    # DB 컬럼명과 일치 (room 테이블 + branch(name) join)
    name: str = Field(description="합주실 룸 이름 (예: 블랙룸, A룸)")
    branch: str = Field(description="지점명 (예: 홍대점, 사당점)")
    business_id: str = Field(description="네이버 플레이스 비즈니스 ID (업체 식별자)")
    biz_item_id: str = Field(description="네이버 예약 상품 ID (룸 식별자)")

    imageUrls: List[str] = Field(default_factory=list, alias="image_urls", description="List of room image URLs")
    maxCapacity: int = Field(alias="max_capacity", description="Maximum capacity")
    recommendCapacity: int = Field(alias="recommend_capacity", description="Recommended capacity")

    @field_validator('recommendCapacity', mode='before')
    @classmethod
    def normalize_recommend_capacity(cls, v: Any) -> int:
        """레거시 데이터 호환: 리스트로 들어올 경우 첫 번째 값을 사용"""
        if isinstance(v, list):
            return v[0] if v else 0
        return v

    # 신규 필드 추가 (v2.0.0 Metadata)
    recommendCapacityRange: Optional[List[int]] = Field(None, alias="recommend_capacity_range", description="Recommended capacity range [min, max]")
    priceConfig: Optional[List[Dict[str, Any]]] = Field(None, alias="price_config", description="Dynamic price configuration")
    
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


# Policy Warning DTO
class PolicyWarning(BaseModel):
    """예약 정책 위반 경고"""
    type: str = Field(..., description="Warning type (call_required, limit_exceeded, etc.)")
    message: str = Field(..., description="User-friendly warning message")

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
    
    # [v2.0.0] 계산된 정보
    estimatedPrice: Optional[int] = None
    policyWarnings: List[PolicyWarning] = Field(default_factory=list)
    
# Crawler Result DTO (Internal Logic Use Only)
class RoomAvailability(RoomDetail):
    """Availability information for a single room (Flattened Structure)"""
    model_config = ConfigDict(
        title="RoomAvailabilityInfo",
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "name": "A룸",
                "branch": "그라운드합주실 신촌1호점",
                "business_id": "1182602",
                "biz_item_id": "5979448",
                "imageUrls": ["https://example.com/ground_a_room.jpg"],
                "maxCapacity": 10,
                "recommendCapacity": 5,
                "pricePerHour": 15000,
                "canReserveOneHour": True,
                "requiresCallOnSameDay": False,
                "available": True,
                "available_slots": {"18:00": True, "19:00": True},
                "estimated_price": 30000,
                "policy_warnings": []
            }
        }
    )

    # RoomDetail 필드들은 상속받음
    available: Union[bool, str] = Field(..., description="예약 가능 여부 (true: 가능, false: 불가, unknown: 확인 필요)")
    available_slots: Dict[str, Union[bool, str]] = Field(..., description="시간대별 예약 가능 여부 (Key: HH:MM)")
    
    # [v2.0.0] 추가 정보
    estimated_price: Optional[int] = Field(None, description="예상 결제 금액 (옵션/인원 추가 요금 포함)")
    policy_warnings: List[PolicyWarning] = Field(default_factory=list, description="예약 정책 위반 경고 (1시간 예약 불가, 당일 전화 문의 등)")

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
    model_config = ConfigDict(
        title="MapAvailabilityResponse",
        json_schema_extra={
            "example": {
                "date": "2025-08-23",
                "start_hour": "18:00",
                "end_hour": "20:00",
                "rooms": [
                    {
                        "name": "A룸",
                        "branch": "그라운드합주실 신촌1호점",
                        "business_id": "1182602",
                        "biz_item_id": "5979448",
                        "imageUrls": [
                            "https://example.com/ground_a_room.jpg"
                        ],
                        "maxCapacity": 10,
                        "recommendCapacity": 5,
                        "baseCapacity": 4,
                        "extraCharge": 2000,
                        "pricePerHour": 15000,
                        "canReserveOneHour": True,
                        "requiresCallOnSameDay": False,
                        "available": True,
                        "available_slots": {"18:00": True, "19:00": True}
                    },
                    {
                        "name": "B룸",
                        "branch": "그라운드합주실 신촌1호점",
                        "business_id": "1182602",
                        "biz_item_id": "5979471",
                        "imageUrls": [
                            "https://example.com/ground_b_room.jpg"
                        ],
                        "maxCapacity": 8,
                        "recommendCapacity": 4,
                        "baseCapacity": None,
                        "extraCharge": None,
                        "pricePerHour": 12000,
                        "canReserveOneHour": True,
                        "requiresCallOnSameDay": False,
                        "available": True,
                        "available_slots": {"18:00": True, "19:00": True}
                    }
                ],
                "branch_summary": {
                    "1182602": {
                        "min_price": 12000,
                        "available_count": 3,
                        "lat": 37.5560505,
                        "lng": 126.9409629
                    }
                }
            }
        }
    )

    date: str = Field(..., description="Checked date")
    start_hour: str = Field(..., description="Checked start time")
    end_hour: str = Field(..., description="Checked end time")
    
    # 기존 필드 유지
    hour_slots: List[str] = Field(default_factory=list, description="List of checked hour slots")
    available_biz_item_ids: List[str] = Field(default_factory=list, description="List of available biz_item_ids")
    rooms: List[RoomAvailability] = Field(..., description="List of rooms with availability info")
    
    # 지도 검색을 위한 신규 필드
    branch_summary: Dict[str, BranchStats] = Field(default_factory=dict, description="Summary stats per branch for map markers")



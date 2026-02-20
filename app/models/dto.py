from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import List, Dict, Union, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import re

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
    
    @field_validator('start_hour', 'end_hour')
    @classmethod
    def validate_hour_format(cls, v: str) -> str:
        if not re.match(r"^(0[0-9]|1[0-9]|2[0-4]):00$", v):
            raise ValueError(f"시간은 'HH:00' 포맷(정각)으로 입력해야 합니다. (잘못된 입력: {v})")
        return v

    @model_validator(mode='after')
    def validate_time_range(self) -> 'AvailabilityRequest':
        start_h = int(self.start_hour.split(':')[0])
        end_h = int(self.end_hour.split(':')[0])
        if start_h >= end_h:
            raise ValueError(f"종료 시간({self.end_hour})은 시작 시간({self.start_hour})보다 최소 1시간 이후여야 합니다.")
        
        # 날짜 및 과거/미래 제한 로직 검증 (KST 기준)
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", self.date):
            raise ValueError(f"날짜 형식이 올바르지 않습니다. (YYYY-MM-DD 포맷 필요, 입력값: {self.date})")
        try:
            req_date = datetime.strptime(self.date, "%Y-%m-%d").date()
        except ValueError as err:
            raise ValueError(f"날짜 형식이 올바르지 않습니다. (YYYY-MM-DD 포맷 필요, 입력값: {self.date})") from err
        
        kst = ZoneInfo("Asia/Seoul")
        now_kst = datetime.now(kst)
        today = now_kst.date()
        
        if req_date < today:
            raise ValueError(f"과거 날짜({self.date})는 예약할 수 없습니다.")
        
        # 오늘 날짜인데 지나간 시간 예약 방지
        current_hour = now_kst.hour
        if req_date == today and start_h <= current_hour:
            raise ValueError(f"오늘({self.date}) 예약 시, 시작 시간({self.start_hour})은 현재 시간({current_hour}시) 이후여야 합니다.")
        
        # 최대 60일 미래까지만 허용
        MAX_Future_Days = 60
        delta_days = (req_date - today).days
        if delta_days > MAX_Future_Days:
            raise ValueError(f"예약 가능일은 최대 {MAX_Future_Days}일 이내입니다. (요청일: {self.date}, {delta_days}일 후)")
            
        return self
    
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
class RoomAvailability(BaseModel):
    """Availability information for a single room (Internal Use)"""
    room_detail: RoomDetail = Field(..., description="Room detail information")
    available: Union[bool, str] = Field(..., description="Availability status (true/false/unknown)")
    available_slots: Dict[str, Union[bool, str]] = Field(..., description="Availability by time slot")
    
    # [v2.0.0] 추가 정보
    estimated_price: Optional[int] = Field(None, description="Calculated total price")
    policy_warnings: List[PolicyWarning] = Field(default_factory=list, description="Policy violation warnings")

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



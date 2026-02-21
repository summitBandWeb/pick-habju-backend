import re
from datetime import datetime, date

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import List, Dict, Union, Any, Optional, ClassVar

# Room Information DTO (DB Query Result)
class RoomDetail(BaseModel):
    """Room detail information (DB column mapping with branch join)"""
    model_config = ConfigDict(populate_by_name=True)
    MANUAL_REVIEW_CAPACITY_FLAG: ClassVar[int] = 100
    BRANCH_FALLBACK_NAME: ClassVar[str] = "지점 정보 없음"

    # DB 컬럼명과 일치 (room 테이블 + branch(name) join)
    name: str = Field(description="Rehearsal room name")
    branch: str = Field(description="Branch name (extracted from join)")
    business_id: str = Field(description="Naver Booking Business ID")
    biz_item_id: str = Field(description="Naver Booking Room ID")

    imageUrls: List[str] = Field(default_factory=list, alias="image_urls", description="List of room image URLs")
    maxCapacity: int = Field(alias="max_capacity", description="Maximum capacity")
    recommendCapacity: int = Field(alias="recommend_capacity", description="Recommended capacity")

    @field_validator("recommendCapacity", mode="before")
    @classmethod
    def normalize_recommend_capacity(cls, v: Any) -> int:
        """레거시 데이터 호환: 리스트로 들어오면 첫 번째 값을 사용"""
        if isinstance(v, list):
            return v[0] if v else 0
        return v

    recommendCapacityRange: Optional[List[int]] = Field(
        default=None,
        alias="recommend_capacity_range",
        description="Recommended capacity range [min, max]",
    )
    baseCapacity: Optional[int] = Field(None, alias="base_capacity", description="Base capacity for extra charge")
    extraCharge: Optional[int] = Field(None, alias="extra_charge", description="Extra charge per person")

    # v2.0.0 유연한 정책 필드 (dict/list 모두 수용)
    priceConfig: Union[Dict[str, Any], List[Dict[str, Any]]] = Field(
        default_factory=dict,
        alias="price_config",
        description="Flexible price configuration (JSON)",
    )
    minCapacity: int = Field(default=1, alias="min_capacity", description="Minimum capacity for reservation")
    minHours: int = Field(default=1, alias="min_hours", description="Minimum reservation hours")
    maxHours: Optional[int] = Field(None, alias="max_hours", description="Maximum reservation hours")
    
    # Branch 정보 확장
    lat: Optional[float] = Field(None, description="Branch latitude")
    lng: Optional[float] = Field(None, description="Branch longitude")
    phoneNumber: Optional[str] = Field(None, description="Branch phone number (if null, use chat)")
    displayName: Optional[str] = Field(None, description="Branch display name")
    openWaitRule: Dict[str, Any] = Field(default_factory=dict, description="Branch open wait rule (JSON)")

    pricePerHour: int = Field(alias="price_per_hour", description="Price per hour (KRW)")
    canReserveOneHour: bool = Field(alias="can_reserve_one_hour", description="Whether 1-hour reservation is available")
    requiresCallOnSameDay: bool = Field(alias="requires_call_on_sameday", description="Whether same-day reservation requires a call")

    @field_validator('branch', mode='before')
    @classmethod
    def extract_branch_info(cls, v: Any) -> str:
        """Supabase join 결과 정제"""
        if isinstance(v, dict):
            v = v.get('name', '')
        if v is None or (isinstance(v, str) and not v.strip()):
            return cls.BRANCH_FALLBACK_NAME
        return v

    @field_validator('imageUrls', mode='before')
    @classmethod
    def handle_null_image_urls(cls, v: Any) -> List[str]:
        """DB에서 null로 오는 image_urls를 빈 리스트로 변환"""
        if v is None:
            return []
        return v

    @field_validator('priceConfig', 'openWaitRule', mode='before')
    @classmethod
    def handle_null_json(cls, v: Any) -> Dict[str, Any]:
        """DB에서 null로 오는 JSON 필드를 빈 딕셔너리로 변환"""
        if v is None:
            return {}
        return v

    @field_validator("recommendCapacityRange", mode="before")
    @classmethod
    def parse_recommend_capacity_range(cls, v: Any) -> Optional[List[int]]:
        """PostgreSQL int4range/문자열/리스트 입력을 [min, max] 형태로 정규화"""
        if v is None:
            return None
        if isinstance(v, list):
            if len(v) == 2:
                return [int(v[0]), int(v[1])]
            return None
        if isinstance(v, str):
            # NOTE: DB backfill/int4range는 inclusive("[]")만 사용하므로 해당 형식만 허용
            match = re.fullmatch(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]", v)
            if not match:
                return None
            lower = int(match.group(1))
            upper = int(match.group(2))
            return [lower, upper]
        return None

    @model_validator(mode="after")
    def populate_v2_fields(self) -> "RoomDetail":
        """V2 호환 필드를 채우고 수동검토 플래그 값을 안전한 응답값으로 변환"""
        if (
            self.recommendCapacityRange
            and len(self.recommendCapacityRange) == 2
            and self.recommendCapacityRange[0] == self.MANUAL_REVIEW_CAPACITY_FLAG
            and self.recommendCapacityRange[1] == self.MANUAL_REVIEW_CAPACITY_FLAG
        ):
            self.recommendCapacityRange = None

        if self.maxCapacity == self.MANUAL_REVIEW_CAPACITY_FLAG:
            self.maxCapacity = 0

        if self.recommendCapacity == self.MANUAL_REVIEW_CAPACITY_FLAG:
            self.recommendCapacity = 0

        if (
            not self.recommendCapacityRange
            and self.recommendCapacity
            and self.recommendCapacity > 0
        ):
            min_cap = max(1, self.recommendCapacity - 2)
            self.recommendCapacityRange = [min_cap, self.recommendCapacity]

        if not self.priceConfig and self.pricePerHour:
            self.priceConfig = {"default": self.pricePerHour, "overrides": []}

        return self

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

    @field_validator("date")
    @classmethod
    def validate_date_regex(cls, value: str) -> str:
        """YYYY-MM-DD 형식 + 실제 달력 유효 날짜를 검증"""
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("date must match YYYY-MM-DD")
        try:
            input_date = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("date must be a valid YYYY-MM-DD calendar date") from exc
        if input_date < date.today():
            raise ValueError("past dates are not allowed")
        return value

    @field_validator("start_hour", "end_hour")
    @classmethod
    def validate_time_format(cls, value: str) -> str:
        if not re.fullmatch(r"^([01]\d|2[0-3]):([0-5]\d)$", value):
            raise ValueError("time must match HH:MM (00:00~23:59)")
        return value

    @field_validator("capacity")
    @classmethod
    def validate_capacity_range(cls, value: int) -> int:
        """합주실 요청 인원수는 1~50 범위만 허용"""
        if not 1 <= value <= 50:
            raise ValueError("capacity must be between 1 and 50")
        return value

    @model_validator(mode="after")
    def validate_logic(self) -> "AvailabilityRequest":
        if not (-90 <= self.swLat <= 90) or not (-90 <= self.neLat <= 90):
            raise ValueError("latitude must be between -90 and 90")
        if not (-180 <= self.swLng <= 180) or not (-180 <= self.neLng <= 180):
            raise ValueError("longitude must be between -180 and 180")
        if self.swLat >= self.neLat:
            raise ValueError("swLat must be less than neLat")
        if self.swLng >= self.neLng:
            raise ValueError("swLng must be less than neLng")

        start = datetime.strptime(self.start_hour, "%H:%M")
        end = datetime.strptime(self.end_hour, "%H:%M")
        if start >= end:
            raise ValueError("start_hour must be earlier than end_hour")

        input_date = datetime.strptime(self.date, "%Y-%m-%d").date()
        if input_date == date.today() and start.time() <= datetime.now().time():
            raise ValueError("past time is not allowed for today")

        return self


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
    recommendCapacityRange: Optional[List[int]] = Field(
        default=None,
        description="Recommended capacity range [min, max]",
    )
    recommendCapacityMin: int = Field(..., description="Calculated min recommend capacity")
    recommendCapacityMax: int = Field(..., description="Calculated max recommend capacity")
    
    baseCapacity: Optional[int] = None
    extraCharge: Optional[int] = None
    pricePerHour: int
    canReserveOneHour: bool
    requiresCallOnSameDay: bool
    
    # v2.0.0 추가 필드
    minCapacity: int
    minHours: int
    maxHours: Optional[int] = None
    phoneNumber: Optional[str] = None
    displayName: Optional[str] = None

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

import re
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator, AliasChoices
import logging
from typing import List, Dict, Union, Any, Optional, ClassVar, Literal

class HealthResponse(BaseModel):
    """Health Check Response Model"""
    status: Literal["healthy", "degraded", "unhealthy"] = Field(description="Health status of the system (healthy, degraded, unhealthy)")
    dependencies: Dict[str, str] = Field(description="Health status of individual dependencies (e.g., database)")

logger = logging.getLogger(__name__)

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
    # [이슈 6] recommendCapacity(단일값 레거시) 제거. 범위형 recommendCapacityRange로 단일화.
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
    phoneNumber: Optional[str] = Field(None, alias="phone_number", description="Branch phone number (if null, use chat)")
    displayName: Optional[str] = Field(None, alias="display_name", description="Branch display name")
    openWaitRule: Dict[str, Any] = Field(default_factory=dict, alias="open_wait_rule", description="Branch open wait rule (JSON)")
    standbyDays: Optional[int] = Field(None, alias="standby_days", description="오픈대기일수 (현재일 기준 N일 이후 오픈 대기 여부 판단용)")

    pricePerHour: int = Field(alias="price_per_hour", description="Price per hour (KRW)")
    # NOTE: 아래 두 필드는 내부 정책 판별 로직에서만 사용하며, 프론트엔드 응답에서는 policy_warnings로 대체됨
    canReserveOneHour: bool = Field(alias="can_reserve_one_hour", description="Whether 1-hour reservation is available", exclude=True)
    # [이슈 1] Python 필드명: requiresCallOnSameDay → requiresContactOnSameDay (전화뿐 아닌 모든 연락수단 포함)
    # NOTE: AliasChoices로 DB 컬럼명 변경 전/후 모두 허용.
    #       - 신규: requires_contact_on_sameday (DB 마이그레이션 완료 후 사용)
    #       - 구형: requires_call_on_sameday    (기존 DB 컬럼명, 마이그레이션 후 이 항목 제거)
    #       TODO: DB 마이그레이션 완료 후 AliasChoices에서 requires_call_on_sameday 제거
    requiresContactOnSameDay: bool = Field(
        validation_alias=AliasChoices(
            "requires_contact_on_sameday",
            "requires_call_on_sameday",
        ),
        description="당일 예약 시 연락(전화/채팅) 필요 여부",
        exclude=True,
    )

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
            logger.warning(f"[dto_validation] Invalid recommend_capacity_range list length: {len(v)} (value: {v})")
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

        # [이슈 6] recommendCapacity(단일값) fallback 로직 제거.
        # recommendCapacityRange가 None이면 그대로 None. 파서/DB 보강으로 해결.

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
            raise ValueError("날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)")
        try:
            input_date = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)") from exc
        if input_date < date.today():
            raise ValueError("과거 날짜는 예약할 수 없습니다.")
        return value

    @field_validator("start_hour")
    @classmethod
    def validate_start_time_format(cls, value: str) -> str:
        """시작 시간 형식(HH:MM, 00:00~23:59)을 검증한다.

        Args:
            value: 시작 시간 문자열.

        Returns:
            str: 검증을 통과한 시작 시간 문자열.

        Raises:
            ValueError: HH:MM 형식에 맞지 않을 때 발생.
        """
        if not re.fullmatch(r"^([01]\d|2[0-3]):([0-5]\d)$", value):
            raise ValueError("시간 형식이 올바르지 않습니다. (HH:MM, 00:00~23:59)")
        return value

    @field_validator("end_hour")
    @classmethod
    def validate_end_time_format(cls, value: str) -> str:
        """종료 시간 형식(HH:MM, 00:00~24:00)을 검증한다.

        Args:
            value: 종료 시간 문자열.

        Returns:
            str: 검증을 통과한 종료 시간 문자열.

        Raises:
            ValueError: HH:MM 형식에 맞지 않을 때 발생.
        """
        if not re.fullmatch(r"^(([01]\d|2[0-3]):([0-5]\d)|24:00)$", value):
            raise ValueError("종료 시간 형식이 올바르지 않습니다. (HH:MM, 00:00~24:00)")
        return value

    @field_validator("capacity")
    @classmethod
    def validate_capacity_range(cls, value: int) -> int:
        """합주실 요청 인원수는 1~50 범위만 허용"""
        if not 1 <= value <= 50:
            raise ValueError("인원은 1명 이상 50명 이하여야 합니다.")
        return value

    @model_validator(mode="after")
    def validate_logic(self) -> "AvailabilityRequest":
        """합주실 검색 요청(AvailabilityRequest)의 위경도 및 시간 유효성을 검증합니다.

        Returns:
            AvailabilityRequest: 유효성 검증을 통과한 인스턴스 자신.

        Raises:
            ValueError: 위경도 범위를 벗어나거나, 종료 시간이 시작 시간보다 빠르거나(심야 별도),
                        최대 5시간을 초과하는 등 주요 예약 정책 위반 시 발생.

        Rationale (의도):
            API 진입점(DTO 계층)에서 올바른 지도 좌표 범위를 선제적으로 검사하고,
            단순 시간 입력 실수(예: 15:00~13:00)와 정상적인 심야 예약(예: 23:00~02:00)을 
            명확히 구분하여 사용자 친화적인 에러를 반환하기 위해 설계되었습니다.
        """
        if not (-90 <= self.swLat <= 90) or not (-90 <= self.neLat <= 90):
            raise ValueError("위도는 -90도에서 90도 사이여야 합니다.")
        if not (-180 <= self.swLng <= 180) or not (-180 <= self.neLng <= 180):
            raise ValueError("경도는 -180도에서 180도 사이여야 합니다.")
        if self.swLat >= self.neLat:
            raise ValueError("남서쪽 위도(swLat)는 북동쪽 위도(neLat)보다 작아야 합니다.")
        if self.swLng >= self.neLng:
            raise ValueError("남서쪽 경도(swLng)는 북동쪽 경도(neLng)보다 작아야 합니다.")

        start_minutes = int(self.start_hour[:2]) * 60 + int(self.start_hour[3:])
        end_minutes = 1440 if self.end_hour == "24:00" else int(self.end_hour[:2]) * 60 + int(self.end_hour[3:])
        
        if start_minutes == end_minutes:
            raise ValueError("시작 시간과 종료 시간은 같을 수 없습니다. (최소 1시간 이상)")

        # 자정을 넘기는 케이스 처리 (예: 23:00 -> 02:00)
        if start_minutes > end_minutes:
            # 시작 시간이 19:00 이후이고 종료 시간이 05:00 이하일 때만 밤샘(Overnight) 의도로 간주 (05:00 포함)
            is_intended_overnight = (start_minutes >= 1140) and (end_minutes <= 300)
            
            if is_intended_overnight:
                end_minutes += 1440
            else:
                raise ValueError("종료 시간이 시작 시간보다 빠를 수 없습니다.")
                
        if (end_minutes - start_minutes) > 300:
            raise ValueError("최대 5시간까지만 예약할 수 있습니다.")

        input_date = datetime.strptime(self.date, "%Y-%m-%d").date()
        if input_date == date.today():
            now_time = datetime.now()
            now_minutes = now_time.hour * 60 + now_time.minute
            if start_minutes <= now_minutes:
                raise ValueError("이미 지나간 시간은 예약할 수 없습니다.")

        return self


# Policy Warning DTO
class PolicyWarning(BaseModel):
    """예약 정책 위반 경고"""
    type: str = Field(..., description="Warning type (call_required, limit_exceeded, etc.)")
    message: str = Field(..., description="User-friendly warning message")



# Crawler Result DTO (Internal Logic Use Only)
class RoomAvailability(BaseModel):
    """Availability information for a single room (Internal Use)"""
    room_detail: RoomDetail = Field(..., description="Room detail information")
    available: bool = Field(..., description="Availability status (true: Available, false: Unavailable or Partial)")
    available_slots: Dict[str, bool] = Field(..., description="Availability by time slot")
    
    # [v2.0.0] 추가 정보
    estimated_price: Optional[int] = Field(None, description="Calculated total price")
    policy_warnings: List[PolicyWarning] = Field(default_factory=list, description="Policy violation warnings")

# Branch-grouped Response DTOs
class RoomResponse(BaseModel):
    """지점 하위의 룸 단위 응답"""
    biz_item_id: str
    name: str
    price_per_hour: int
    available: bool = Field(..., description="Availability status (true: Available, false: Unavailable or Partial)")
    available_slots: Dict[str, bool] = Field(..., description="Availability by time slot")
    estimated_price: Optional[int] = None
    image_urls: List[str]
    max_capacity: int
    recommend_capacity: Optional[int] = None
    recommend_capacity_range: Optional[List[int]] = None
    base_capacity: Optional[int] = None
    extra_charge: Optional[int] = None
    min_capacity: int
    min_hours: int
    max_hours: Optional[int] = None
    policy_warnings: List[PolicyWarning] = Field(default_factory=list)

class BranchResponse(BaseModel):
    """지점 단위 응답 (마커 및 리스트 표시용)"""
    business_id: str
    branch: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    min_price_available: Optional[int] = None
    min_price_partial: Optional[int] = None
    available_count: int
    phone_number: Optional[str] = None
    display_name: Optional[str] = None
    rooms: List[RoomResponse] = Field(default_factory=list)

# Full Response DTO (Nested Branch Structure)
class AvailabilityResponse(BaseModel):
    """Response for availability check
    
    프론트엔드 최적화를 위해 지점(Branch) 단위로 룸을 그룹핑하여 반환합니다.
    """
    date: str = Field(..., description="Checked date")
    start_hour: str = Field(..., description="Checked start time")
    end_hour: str = Field(..., description="Checked end time")
    
    hour_slots: List[str] = Field(default_factory=list, description="List of checked hour slots")
    available_biz_item_ids: List[str] = Field(default_factory=list, description="List of available biz_item_ids")
    
    branches: List[BranchResponse] = Field(..., description="List of branches with their available rooms")

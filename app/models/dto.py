from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import List, Dict, Union, Any, Optional
<<<<<<< HEAD
from datetime import datetime
from zoneinfo import ZoneInfo
import re
=======
import re
from datetime import datetime, date
>>>>>>> a126c76e7a07a49c3bbe4218e8613aee9b9d4aef

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

    @field_validator('date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        # 1. Regex Format Check
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)")
        
        # 2. Calendar Validity Check (e.g., 2024-02-30)
        try:
            input_date = datetime.strptime(v, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)")
            
        # 3. Logic Check (Past Date)
        if input_date < date.today():
            raise ValueError("과거 날짜는 예약할 수 없습니다.")
            
        return v
    
    @field_validator('start_hour', 'end_hour')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        # HH:MM 형식 확인 (00:00 ~ 23:59)
        if not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", v):
            raise ValueError(f"시간 형식이 올바르지 않습니다. (HH:MM, 00:00~23:59): {v}")
        return v

    @field_validator('capacity')
    @classmethod
    def validate_capacity_range(cls, v: int) -> int:
        if not (1 <= v <= 100):
            raise ValueError("인원은 1명 이상 100명 이하여야 합니다.")
        return v

    @model_validator(mode='after')
    def validate_logic(self) -> 'AvailabilityRequest':
        # 1. Coordinate Range & Logic
        # Latitude: -90 ~ 90
        if not (-90 <= self.swLat <= 90) or not (-90 <= self.neLat <= 90):
            raise ValueError("위도는 -90도에서 90도 사이여야 합니다.")
            
        # Longitude: -180 ~ 180
        if not (-180 <= self.swLng <= 180) or not (-180 <= self.neLng <= 180):
            raise ValueError("경도는 -180도에서 180도 사이여야 합니다.")

        if self.swLat >= self.neLat:
            raise ValueError("남서쪽 위도(swLat)는 북동쪽 위도(neLat)보다 작아야 합니다.")
        if self.swLng >= self.neLng:
            raise ValueError("남서쪽 경도(swLng)는 북동쪽 경도(neLng)보다 작아야 합니다.")
            
        # 2. Time Logic (Start < End & Past Time)
        # NOTE: field_validator에서 정규식으로 형식을 보장하므로 strptime은 실패하지 않음
        start = datetime.strptime(self.start_hour, "%H:%M")
        end = datetime.strptime(self.end_hour, "%H:%M")
        
        if start >= end:
            raise ValueError("시작 시간은 종료 시간보다 빨라야 합니다.")
        
        # 과거 시간 체크 (오늘인 경우)
        input_date = datetime.strptime(self.date, "%Y-%m-%d").date()
        if input_date == date.today():
            now_time = datetime.now().time()
            # 시작 시간이 현재 시간보다 이전이면 에러
            if start.time() <= now_time:
                raise ValueError("이미 지나간 시간은 예약할 수 없습니다.")
                
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



from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import List, Dict, Union, Any, Optional
import re
from datetime import datetime, date

# Room Information DTO (DB Query Result)
class RoomDetail(BaseModel):
    """Room detail information (DB column mapping with branch join)"""
    model_config = ConfigDict(populate_by_name=True)

    # DB 컬럼명과 일치 (room 테이블 + branch(name) join)
    name: str = Field(description="합주실 룸 이름 (예: 블랙룸, A룸)")
    branch: str = Field(description="지점명 (예: 홍대점, 사당점)")
    business_id: str = Field(description="네이버 플레이스 비즈니스 ID (업체 식별자)")
    biz_item_id: str = Field(description="네이버 예약 상품 ID (룸 식별자)")

    imageUrls: List[str] = Field(default_factory=list, alias="image_urls", description="룸 이미지 URL 목록 (네이버 예약 페이지에서 수집, 빈 배열일 수 있음)")
    maxCapacity: int = Field(alias="max_capacity", description="최대 수용 인원 (이 인원을 초과하면 예약 불가)")
    recommendCapacity: int = Field(alias="recommend_capacity", description="권장 인원 (쾌적하게 합주할 수 있는 적정 인원)")

    @field_validator('recommendCapacity', mode='before')
    @classmethod
    def normalize_recommend_capacity(cls, v: Any) -> int:
        """레거시 데이터 호환: 리스트로 들어올 경우 첫 번째 값을 사용"""
        if isinstance(v, list):
            return v[0] if v else 0
        return v

    # 신규 필드 추가 (v2.0.0 Metadata)
    recommendCapacityRange: Optional[List[int]] = Field(None, alias="recommend_capacity_range", description="권장 인원 범위 [최소, 최대] (예: [3, 5])")
    priceConfig: Optional[List[Dict[str, Any]]] = Field(None, alias="price_config", description="시간대별 차등 요금 설정 (야간/주말 할증 등, null이면 단일 요금제)")
    
    baseCapacity: Optional[int] = Field(None, alias="base_capacity", description="기본 인원 (이 인원까지는 추가 요금 없음, null이면 추가 요금 정책 없음)")
    extraCharge: Optional[int] = Field(None, alias="extra_charge", description="기본 인원 초과 시 1인당 추가 요금 (원 단위, null이면 추가 요금 없음)")
    lat: Optional[float] = Field(None, description="지점 위도 (지도 마커 표시용)")
    lng: Optional[float] = Field(None, description="지점 경도 (지도 마커 표시용)")

    pricePerHour: int = Field(alias="price_per_hour", description="시간당 기본 요금 (원 단위, 예: 15000)")
    canReserveOneHour: bool = Field(alias="can_reserve_one_hour", description="1시간 단위 예약 가능 여부 (false면 최소 2시간 이상 예약 필요, 1시간 예약 시 전화 문의 필요)")
    requiresCallOnSameDay: bool = Field(alias="requires_call_on_sameday", description="당일 예약 시 전화 문의 필요 여부 (true면 당일 온라인 예약 불가, 전화로만 가능)")

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
    """예약 정책 위반 경고

    FE에서 이 경고가 존재하면 사용자에게 안내 메시지를 표시해야 합니다.
    예약 자체는 가능하지만, 추가 조건(전화 문의 등)이 필요한 경우에 발생합니다.

    Rationale:
        합주실마다 예약 정책이 다르므로(1시간 예약 불가, 당일 전화 예약만 가능 등),
        크롤링 시점에 해당 정책을 감지하여 FE에 전달합니다.
    """
    type: str = Field(
        ...,
        description="경고 유형 코드. 가능한 값: "
                    "'call_required_1h' (1시간 예약 시 전화 문의 필요), "
                    "'call_required_today' (당일 예약 시 전화 문의 필요)"
    )
    message: str = Field(
        ...,
        description="사용자에게 직접 노출 가능한 안내 메시지 (예: '1시간 예약은 전화 문의가 필요합니다.')"
    )

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
    """Availability information for a single room (Nested Structure)"""
    model_config = ConfigDict(
        title="RoomAvailabilityInfo",
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "room_detail": {
                    "name": "A룸",
                    "branch": "그라운드합주실 신촌1호점",
                    "business_id": "1182602",
                    "biz_item_id": "5979448",
                    "image_urls": ["https://example.com/ground_a_room.jpg"],
                    "max_capacity": 10,
                    "recommend_capacity": 5,
                    "recommend_capacity_range": [3, 5],
                    "price_config": [],
                    "base_capacity": 4,
                    "extra_charge": 2000,
                    "lat": 37.5560505,
                    "lng": 126.9409629,
                    "price_per_hour": 15000,
                    "can_reserve_one_hour": True,
                    "requires_call_on_sameday": False
                },
                "available": True,
                "available_slots": {"18:00": True, "19:00": True},
                "estimated_price": 30000,
                "policy_warnings": []
            }
        }
    )

    room_detail: RoomDetail = Field(..., description="Room detail information")
    available: Union[bool, str] = Field(..., description="예약 가능 여부 (true: 가능, false: 불가, unknown: 확인 필요)")
    available_slots: Dict[str, Union[bool, str]] = Field(..., description="시간대별 예약 가능 여부 (Key: HH:MM)")
    
    # [v2.0.0] 추가 정보
    estimated_price: Optional[int] = Field(None, description="예상 결제 금액 (옵션/인원 추가 요금 포함)")
    policy_warnings: List[PolicyWarning] = Field(default_factory=list, description="예약 정책 위반 경고 (1시간 예약 불가, 당일 전화 문의 등)")

# Branch Summary Stat Model
class BranchStats(BaseModel):
    """지점별 요약 정보"""
    min_price: int = Field(..., description="해당 지점 내 최저 시간당 요금 (원 단위, 지도 마커에 표시)")
    available_count: int = Field(..., description="해당 지점에서 예약 가능한 룸 수")
    lat: Optional[float] = Field(None, description="지점 위도 (지도 마커 좌표)")
    lng: Optional[float] = Field(None, description="지점 경도 (지도 마커 좌표)")

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
                "start_hour": "14:00",
                "end_hour": "16:00",
                "hour_slots": [
                    "14:00",
                    "15:00"
                ],
                "available_biz_item_ids": [
                    "5979448",
                    "5979471"
                ],
                "rooms": [
                    {
                        "room_detail": {
                            "name": "A룸",
                            "branch": "그라운드합주실 신촌1호점",
                            "business_id": "1182602",
                            "biz_item_id": "5979448",
                            "image_urls": [
                                "https://example.com/ground_a_room.jpg"
                            ],
                            "max_capacity": 10,
                            "recommend_capacity": 5,
                            "recommend_capacity_range": [3, 5],
                            "price_config": [],
                            "base_capacity": 4,
                            "extra_charge": 2000,
                            "lat": 37.5560505,
                            "lng": 126.9409629,
                            "price_per_hour": 15000,
                            "can_reserve_one_hour": True,
                            "requires_call_on_sameday": False
                        },
                        "available": True,
                        "available_slots": {
                            "14:00": True,
                            "15:00": True
                        },
                        "estimated_price": 30000,
                        "policy_warnings": []
                    },
                    {
                        "room_detail": {
                            "name": "B룸",
                            "branch": "그라운드합주실 신촌1호점",
                            "business_id": "1182602",
                            "biz_item_id": "5979471",
                            "image_urls": [
                                "https://example.com/ground_b_room.jpg"
                            ],
                            "max_capacity": 8,
                            "recommend_capacity": 4,
                            "recommend_capacity_range": [3, 4],
                            "price_config": [],
                            "base_capacity": None,
                            "extra_charge": None,
                            "lat": 37.5560505,
                            "lng": 126.9409629,
                            "price_per_hour": 12000,
                            "can_reserve_one_hour": True,
                            "requires_call_on_sameday": False
                        },
                        "available": True,
                        "available_slots": {
                            "14:00": True,
                            "15:00": True
                        },
                        "estimated_price": 24000,
                        "policy_warnings": []
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



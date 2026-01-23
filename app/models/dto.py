from pydantic import BaseModel, Field
from typing import List, Dict, Union, Literal, Optional

# 요청 DTO
class RoomKey(BaseModel):
    """합주실 룸 식별 정보"""
    name: str = Field(..., description="합주실 룸 이름", examples=["블랙룸"])
    branch: str = Field(..., description="합주실 지점 이름", examples=["비쥬 합주실 1호점"])
    business_id: str = Field(..., description="네이버 예약 지점 ID", examples=["522011"])
    biz_item_id: str = Field(..., description="네이버 예약 룸 ID", examples=["3968885"])
    # Phase 2 추가 필드
    price_per_hour: Optional[int] = Field(None, description="시간당 가격 (원)")
    max_capacity: Optional[int] = Field(None, description="최대 수용 인원")
    recommend_capacity: Optional[int] = Field(None, description="권장 인원")
    image_urls: Optional[List[str]] = Field(None, description="룸 이미지 URL 목록")

    model_config = {"json_schema_extra": {"examples": [{"name": "블랙룸", "branch": "비쥬 합주실 1호점", "business_id": "522011", "biz_item_id": "3968885"}]}}

class AvailabilityRequest(BaseModel):
    """예약 가능 여부 조회 요청"""
    date: str = Field(..., description="예약 날짜 (YYYY-MM-DD)", examples=["2025-07-03"])
    hour_slots: List[str] = Field(..., description="확인할 시간 슬롯 목록", examples=[["15:00", "16:00"]])
    rooms: List[RoomKey] = Field(..., description="조회할 합주실 룸 목록")

# 응답 DTO (단일 방 기준 상세 정보)
class RoomAvailability(BaseModel):
    """단일 룸의 예약 가능 여부 정보"""
    name: str = Field(..., description="합주실 룸 이름")
    branch: str = Field(..., description="합주실 지점 이름")
    business_id: str = Field(..., description="네이버 예약 지점 ID")
    biz_item_id: str = Field(..., description="네이버 예약 룸 ID")
    available: Union[bool, Literal["unknown"]] = Field(..., description="모든 시간 슬롯 예약 가능 여부 (true/false/unknown)")
    available_slots: Dict[str, Union[bool, Literal["unknown"]]] = Field(..., description="시간별 예약 가능 여부", examples=[{"15:00": True, "16:00": False}])
    # Phase 2 추가 필드
    price_per_hour: Optional[int] = Field(None, description="시간당 가격 (원)")
    max_capacity: Optional[int] = Field(None, description="최대 수용 인원")
    recommend_capacity: Optional[int] = Field(None, description="권장 인원")
    image_urls: Optional[List[str]] = Field(None, description="룸 이미지 URL 목록")

# 응답 전체 DTO (요약 필드 포함)
class AvailabilityResponse(BaseModel):
    """예약 가능 여부 조회 응답"""
    date: str = Field(..., description="조회한 날짜")
    hour_slots: List[str] = Field(..., description="조회한 시간 슬롯 목록")
    results: List[RoomAvailability] = Field(..., description="각 룸별 예약 가능 여부")
    available_biz_item_ids: List[str] = Field(..., description="모든 시간 슬롯 예약 가능한 룸 ID 목록 (프론트 편의용)")

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Union, Optional

# Room Information DTO (DB Query Result)
class RoomDetail(BaseModel):
    """Room detail information (DB alias mapping)"""
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(alias="room_name", description="Rehearsal room name")
    branch: str = Field(alias="branch_name", description="Branch name")
    business_id: str = Field(alias="branch_id", description="Naver Booking Business ID")
    biz_item_id: str = Field(alias="room_id", description="Naver Booking Room ID")

    imageUrls: List[str] = Field(default_factory=list, alias="image_urls", description="List of room image URLs")
    maxCapacity: int = Field(alias="max_capacity", description="Maximum capacity")
    recommendCapacity: int = Field(alias="recommend_capacity", description="Recommended capacity")
    pricePerHour: int = Field(alias="price_per_hour", description="Price per hour (KRW)")
    canReserveOneHour: bool = Field(alias="can_reserve_one_hour", description="Whether 1-hour reservation is available")
    requiresCallOnSameDay: bool = Field(alias="requires_call_on_sameday", description="Whether same-day reservation requires a call")

# Request DTO
class AvailabilityRequest(BaseModel):
    """Request for checking availability"""
    date: str = Field(..., description="Reservation date (YYYY-MM-DD)")
    capacity: int = Field(..., description="Number of users")
    start_hour: str = Field(..., description="Start time (HH:MM)")
    end_hour: str = Field(..., description="End time (HH:MM)")

# Response DTO (Single Room Detail)
class RoomAvailability(BaseModel):
    """Availability information for a single room"""
    room_detail: RoomDetail = Field(..., description="Room detail information")
    available: Union[bool, str] = Field(..., description="Availability status (true/false/unknown)")
    available_slots: Dict[str, Union[bool, str]] = Field(..., description="Availability by time slot")

# Full Response DTO (Summary Included)
class AvailabilityResponse(BaseModel):
    """Response for availability check"""
    date: str = Field(..., description="Checked date")
    hour_slots: List[str] = Field(..., description="List of checked time slots")
    results: List[RoomAvailability] = Field(..., description="Availability status per room")
    available_biz_item_ids: List[str] = Field(..., description="List of available room IDs for all time slots (frontend convenience)")

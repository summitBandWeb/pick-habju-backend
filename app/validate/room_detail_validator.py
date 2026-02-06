from typing import List
from app.models.dto import RoomDetail
# [주의] 아래 Exception 파일명과 클래스명도 실제 파일에서 함께 수정해주세요.
from app.exception.common.room_detail_exception import (
    RoomDetailFieldMissingError,
    RoomDetailListEmptyError
)

# --- 단위 검증 함수들 (가장 작은 단위) ---

def validate_list_not_empty(target_rooms: List[RoomDetail]):
    """RoomDetail 리스트가 비어있는지 검증"""
    if not target_rooms:
        raise RoomDetailListEmptyError()

def validate_room_detail_fields(room: RoomDetail):
    """단일 RoomDetail의 필수 필드 누락 검증"""
    if not all([room.business_id, room.biz_item_id, room.name, room.branch]):
        raise RoomDetailFieldMissingError(f"RoomDetail 정보가 누락되었습니다: {room}")

# --- 조합 검증 함수들 ---

def validate_room_detail(room: RoomDetail):
    """
    단일 RoomDetail에 대한 모든 검증을 수행합니다.
    (필드 누락 검증 + 존재 여부 검증)
    """
    validate_room_detail_fields(room)

def validate_room_detail_list(target_rooms: List[RoomDetail]):
    """
    RoomDetail 리스트 전체에 대한 모든 검증을 수행합니다.
    (리스트 비어있는지 검증 + 모든 개별 RoomDetail 검증)
    """
    validate_list_not_empty(target_rooms)
    for room in target_rooms:
        validate_room_detail(room)
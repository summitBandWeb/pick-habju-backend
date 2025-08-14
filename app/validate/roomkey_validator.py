from typing import List
from app.utils.room_loader import load_rooms
from app.models.dto import RoomKey
from app.exception.common.roomkey_exception import RoomKeyFieldMissingError, RoomKeyNotFoundError, RoomKeyListEmptyError

# --- 단위 검증 함수들 (가장 작은 단위) ---

def validate_list_not_empty(rooms: List[RoomKey]):
    """RoomKey 리스트가 비어있는지 검증"""
    if not rooms:
        raise RoomKeyListEmptyError()

def validate_room_key_fields(room: RoomKey):
    """단일 RoomKey의 필수 필드 누락 검증"""
    if not all([room.business_id, room.biz_item_id, room.name, room.branch]):
        raise RoomKeyFieldMissingError(f"RoomKey 정보가 누락되었습니다: {room}")

def validate_room_key_exists(room: RoomKey):
    """단일 RoomKey가 rooms.json에 존재하는지 검증"""
    all_rooms = load_rooms()
    is_found = any(
        r["name"] == room.name and
        r["branch"] == room.branch and
        str(r["business_id"]) == str(room.business_id) and
        str(r["biz_item_id"]) == str(room.biz_item_id)
        for r in all_rooms
    )
    if not is_found:
        raise RoomKeyNotFoundError(f"rooms.json에 해당 RoomKey가 없습니다: {room}")

# --- 조합 검증 함수들 ---

def validate_room_key(room: RoomKey):
    """
    단일 RoomKey에 대한 모든 검증을 수행합니다.
    (필드 누락 검증 + 존재 여부 검증)
    """
    validate_room_key_fields(room)
    validate_room_key_exists(room)

def validate_room_key_list(rooms: List[RoomKey]):
    """
    RoomKey 리스트 전체에 대한 모든 검증을 수행합니다.
    (리스트 비어있는지 검증 + 모든 개별 RoomKey 검증)
    """
    validate_list_not_empty(rooms)
    for room in rooms:
        validate_room_key(room)

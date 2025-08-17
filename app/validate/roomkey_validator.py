from app.utils.room_loader import load_rooms
from app.models.dto import RoomKey
from app.exception.common.roomkey_exception import RoomKeyFieldMissingError, RoomKeyNotFoundError

def validate_room_key_fields(room: RoomKey):
    """RoomKey 필수 필드 누락 검증"""
    if (not room.business_id or
        not room.biz_item_id or
        not room.name or
        not room.branch or
        room.business_id == "" or
        room.biz_item_id == "" or
        room.name == "" or
        room.branch == ""):
        raise RoomKeyFieldMissingError(f"RoomKey 정보가 누락되었습니다: {room}")

def validate_room_key_exists(room: RoomKey):
    """RoomKey가 rooms.json에 존재하는지 검증"""
    rooms = load_rooms()
    found = any(
        r["name"] == room.name and
        r["branch"] == room.branch and
        str(r["business_id"]) == str(room.business_id) and
        str(r["biz_item_id"]) == str(room.biz_item_id)
        for r in rooms
    )
    if not found:
        raise RoomKeyNotFoundError(f"RoomKey를 찾을 수 없습니다: {room.name} ({room.branch})")

def validate_room_key(room: RoomKey):
    """RoomKey 전체 검증(필드 + 존재여부)"""
    validate_room_key_fields(room)
    validate_room_key_exists(room)

import pytest
from app.validate.roomkey_validator import validate_room_key_fields, validate_room_key_exists
from app.exception.common.roomkey_exception import RoomKeyFieldMissingError, RoomKeyNotFoundError
from app.models.dto import RoomKey

def test_validate_room_key_field_missing():
    """RoomKey의 필수 필드가 누락된 경우 RoomKeyFieldMissingError 예외가 발생해야 한다."""
    room = RoomKey(business_id=None, biz_item_id="1", name="A", branch="B")
    with pytest.raises(RoomKeyFieldMissingError):
        validate_room_key_fields(room)

def test_validate_room_key_not_found():
    """rooms.json에 없는 RoomKey는 RoomKeyNotFoundError 예외가 발생해야 한다."""
    room = RoomKey(business_id="999", biz_item_id="999", name="없는방", branch="없는지점")
    with pytest.raises(RoomKeyNotFoundError):
        validate_room_key_exists(room)

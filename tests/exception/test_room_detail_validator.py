import pytest

from app.exception.common.room_detail_exception import (
    RoomDetailFieldMissingError,
    RoomDetailListEmptyError,
)
from app.models.dto import RoomDetail
from app.validate.room_detail_validator import (
    validate_list_not_empty,
    validate_room_detail_fields,
)


def _room(**overrides) -> RoomDetail:
    payload = {
        "business_id": "522011",
        "biz_item_id": "3968885",
        "name": "블랙룸",
        "branch": "비상합주실 1호점",
        "imageUrls": [],
        "maxCapacity": 0,
        "recommendCapacity": 0,
        "pricePerHour": 0,
        "canReserveOneHour": False,
        "requiresCallOnSameDay": False,
    }
    payload.update(overrides)
    return RoomDetail(**payload)


def test_validate_list_empty():
    with pytest.raises(RoomDetailListEmptyError):
        validate_list_not_empty([])


def test_validate_list_not_empty_success():
    validate_list_not_empty([_room()])


@pytest.mark.parametrize(
    "invalid_room",
    [
        _room(business_id=""),
        _room(biz_item_id=""),
        _room(name=""),
    ],
)
def test_validate_room_detail_field_missing(invalid_room: RoomDetail):
    with pytest.raises(RoomDetailFieldMissingError):
        validate_room_detail_fields(invalid_room)


def test_validate_room_detail_fields_allows_empty_branch_with_fallback():
    # branch가 비어도 RoomDetail validator가 fallback branch를 채운다.
    validate_room_detail_fields(_room(branch=""))


def test_validate_room_detail_fields_success():
    validate_room_detail_fields(_room())

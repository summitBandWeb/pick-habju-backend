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
        "image_urls": [],
        "max_capacity": 6,
        "recommend_capacity_range": [3, 5],
        "price_per_hour": 0,
        "can_reserve_one_hour": False,
        # [이슈 1] Python 필드명은 requiresContactOnSameDay이나, 현재 DB 컬럼명인 alias를 사용
        "requires_call_on_sameday": False,
    }
    payload.update(overrides)
    return RoomDetail.model_validate(payload)


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

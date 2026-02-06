import pytest
from app.validate.room_detail_validator import (
    validate_list_not_empty,
    validate_room_detail_fields,
    validate_room_detail_list
)
from app.exception.common.room_detail_exception import RoomDetailFieldMissingError, RoomDetailListEmptyError
from app.models.dto import RoomDetail


# --- 단위 테스트: validate_list_not_empty ---

def test_validate_list_empty():
    """빈 리스트가 주어졌을 때 RoomDetailListEmptyError 예외가 발생해야 한다."""
    with pytest.raises(RoomDetailListEmptyError):
        validate_list_not_empty([])


def test_validate_list_not_empty_success():
    """요소가 있는 리스트는 예외 없이 통과해야 한다."""
    try:
        validate_list_not_empty([RoomDetail(name="A", branch="B", business_id="1", biz_item_id="2", imageUrls=[], maxCapacity=0, recommendCapacity=0, pricePerHour=0, canReserveOneHour=False, requiresCallOnSameDay=False)])
    except RoomDetailListEmptyError:
        pytest.fail("RoomDetailListEmptyError가 예기치 않게 발생했습니다.")


# --- 단위 테스트: validate_room_detail_fields ---

@pytest.mark.parametrize(
    "invalid_room",
    [
        # business_id가 빈 문자열인 경우
        RoomDetail(business_id="", biz_item_id="3968885", name="블랙룸", branch="비쥬합주실 1호점", imageUrls=[], maxCapacity=0, recommendCapacity=0, pricePerHour=0, canReserveOneHour=False, requiresCallOnSameDay=False),
        # biz_item_id가 빈 문자열인 경우
        RoomDetail(business_id="522011", biz_item_id="", name="블랙룸", branch="비쥬합주실 1호점", imageUrls=[], maxCapacity=0, recommendCapacity=0, pricePerHour=0, canReserveOneHour=False, requiresCallOnSameDay=False),
        # name이 빈 문자열인 경우
        RoomDetail(business_id="522011", biz_item_id="3968885", name="", branch="비쥬합주실 1호점", imageUrls=[], maxCapacity=0, recommendCapacity=0, pricePerHour=0, canReserveOneHour=False, requiresCallOnSameDay=False),
        # branch가 빈 문자열인 경우
        RoomDetail(business_id="522011", biz_item_id="3968885", name="블랙룸", branch="", imageUrls=[], maxCapacity=0, recommendCapacity=0, pricePerHour=0, canReserveOneHour=False, requiresCallOnSameDay=False),
    ]
)
def test_validate_room_detail_field_missing(invalid_room: RoomDetail):
    """RoomDetail의 필수 필드가 하나라도 누락된 경우 RoomDetailFieldMissingError 예외가 발생해야 한다."""
    with pytest.raises(RoomDetailFieldMissingError):
        validate_room_detail_fields(invalid_room)


def test_validate_room_detail_fields_success():
    """모든 필드가 유효한 RoomDetail은 예외 없이 통과해야 한다."""
    valid_room = RoomDetail(business_id="522011", biz_item_id="3968885", name="블랙룸", branch="비쥬합주실 1호점", imageUrls=[], maxCapacity=0, recommendCapacity=0, pricePerHour=0, canReserveOneHour=False, requiresCallOnSameDay=False)
    try:
        validate_room_detail_fields(valid_room)
    except RoomDetailFieldMissingError:
        pytest.fail("RoomDetailFieldMissingError가 예기치 않게 발생했습니다.")

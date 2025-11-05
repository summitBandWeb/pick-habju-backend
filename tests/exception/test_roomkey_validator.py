import pytest
from app.validate.roomkey_validator import (
    validate_list_not_empty,
    validate_room_key_fields,
    validate_room_key_exists,
    validate_room_key_list
)
from app.exception.common.roomkey_exception import RoomKeyFieldMissingError, RoomKeyNotFoundError, RoomKeyListEmptyError
from app.models.dto import RoomKey


# --- 단위 테스트: validate_list_not_empty ---

def test_validate_list_empty():
    """빈 리스트가 주어졌을 때 RoomKeyListEmptyError 예외가 발생해야 한다."""
    with pytest.raises(RoomKeyListEmptyError):
        validate_list_not_empty([])


def test_validate_list_not_empty_success():
    """요소가 있는 리스트는 예외 없이 통과해야 한다."""
    try:
        validate_list_not_empty([RoomKey(name="A", branch="B", business_id="1", biz_item_id="2")])
    except RoomKeyListEmptyError:
        pytest.fail("RoomKeyListEmptyError가 예기치 않게 발생했습니다.")


# --- 단위 테스트: validate_room_key_fields ---

@pytest.mark.parametrize(
    "invalid_room",
    [
        # business_id가 빈 문자열인 경우
        RoomKey(business_id="", biz_item_id="3968885", name="블랙룸", branch="비쥬합주실 1호점"),
        # biz_item_id가 빈 문자열인 경우
        RoomKey(business_id="522011", biz_item_id="", name="블랙룸", branch="비쥬합주실 1호점"),
        # name이 빈 문자열인 경우
        RoomKey(business_id="522011", biz_item_id="3968885", name="", branch="비쥬합주실 1호점"),
        # branch가 빈 문자열인 경우
        RoomKey(business_id="522011", biz_item_id="3968885", name="블랙룸", branch=""),
    ]
)
def test_validate_room_key_field_missing(invalid_room: RoomKey):
    """RoomKey의 필수 필드가 하나라도 누락된 경우 RoomKeyFieldMissingError 예외가 발생해야 한다."""
    with pytest.raises(RoomKeyFieldMissingError):
        validate_room_key_fields(invalid_room)


def test_validate_room_key_fields_success():
    """모든 필드가 유효한 RoomKey는 예외 없이 통과해야 한다."""
    valid_room = RoomKey(business_id="522011", biz_item_id="3968885", name="블랙룸", branch="비쥬합주실 1호점")
    try:
        validate_room_key_fields(valid_room)
    except RoomKeyFieldMissingError:
        pytest.fail("RoomKeyFieldMissingError가 예기치 않게 발생했습니다.")


# # --- 단위 테스트: validate_room_key_exists ---

# def test_validate_room_key_not_found(mocker, rooms_data):
#     """rooms.json에 없는 RoomKey는 RoomKeyNotFoundError 예외가 발생해야 한다."""
#     # load_rooms 함수가 실제 파일에서 읽어온 데이터를 반환하도록 설정
#     mocker.patch('app.validate.roomkey_validator.load_rooms', return_value=rooms_data)

#     room = RoomKey(business_id="999", biz_item_id="999", name="없는방", branch="없는지점")
#     with pytest.raises(RoomKeyNotFoundError):
#         validate_room_key_exists(room)


# def test_validate_room_key_exists_success(mocker, rooms_data):
#     """rooms.json에 존재하는 RoomKey는 예외 없이 통과해야 한다."""
#     mocker.patch('app.validate.roomkey_validator.load_rooms', return_value=rooms_data)

#     # 실제 데이터에 있는 RoomKey로 테스트
#     room = RoomKey(name="A룸", branch="그루브 사당점", business_id="sadang", biz_item_id="13")
#     try:
#         validate_room_key_exists(room)
#     except RoomKeyNotFoundError:
#         pytest.fail("RoomKeyNotFoundError가 예기치 않게 발생했습니다.")


# # --- 통합 테스트: validate_room_key_list ---

# def test_validate_room_key_list_success(mocker, rooms_data):
#     """유효한 RoomKey들로 이루어진 리스트는 예외 없이 통과해야 한다."""
#     mocker.patch('app.validate.roomkey_validator.load_rooms', return_value=rooms_data)

#     valid_rooms = [
#         RoomKey(name="블랙룸", branch="비쥬합주실 1호점", business_id="522011", biz_item_id="3968885"),
#         RoomKey(name="V룸", branch="드림합주실 사당점", business_id="dream_sadang", biz_item_id="25")
#     ]
#     try:
#         validate_room_key_list(valid_rooms)
#     except Exception as e:
#         pytest.fail(f"예기치 않은 예외가 발생했습니다: {e}")


# def test_validate_room_key_list_raises_not_found(mocker, rooms_data):
#     """리스트에 존재하지 않는 RoomKey가 포함된 경우 RoomKeyNotFoundError가 발생해야 한다."""
#     mocker.patch('app.validate.roomkey_validator.load_rooms', return_value=rooms_data)

#     invalid_list = [
#         RoomKey(name="블랙룸", branch="비쥬합주실 1호점", business_id="522011", biz_item_id="3968885"),
#         RoomKey(name="없는방", branch="없는지점", business_id="999", biz_item_id="999")  # 유효하지 않은 키
#     ]
#     with pytest.raises(RoomKeyNotFoundError):
#         validate_room_key_list(invalid_list)

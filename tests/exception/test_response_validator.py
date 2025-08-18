import pytest
from app.validate.response_validator import validate_response_rooms
from app.exception.common.response_exception import ResponseMismatchError
from app.models.dto import RoomKey

@pytest.fixture
def all_room_keys(rooms_data):
    """
    conftest.py의 rooms_data 픽스처(dict 리스트)를 사용하여
    RoomKey 객체의 리스트를 생성하는 픽스처입니다.
    이 픽스처는 이 파일 안의 테스트에서만 사용됩니다.
    """
    return [RoomKey(**room) for room in rooms_data]


def test_validate_response_rooms_success(all_room_keys):
    """
    요청: 실제 rooms.json에서 3개 방 선택
    응답: 같은 3개 방을 순서만 바꿔서 전달
    기대: 예외 발생하지 않음 (성공)
    """
    requested = [all_room_keys[0], all_room_keys[1], all_room_keys[2]]
    responded = [all_room_keys[2], all_room_keys[0], all_room_keys[1]]
    validate_response_rooms(requested, responded)


def test_validate_response_rooms_fail_count(all_room_keys):
    """
    요청: 실제 rooms.json에서 3개 방 선택
    응답: 2개만 전달(1개 누락)
    기대: ResponseMismatchError 발생 (누락)
    """
    requested = [all_room_keys[0], all_room_keys[1], all_room_keys[2]]
    responded = [all_room_keys[0], all_room_keys[1]]
    with pytest.raises(ResponseMismatchError) as excinfo:
        validate_response_rooms(requested, responded)
    assert "누락" in str(excinfo.value)


def test_validate_response_rooms_fail_id(all_room_keys):
    """
    요청: 실제 rooms.json에서 3개 방 선택
    응답: 2개는 동일, 1개는 다른 방으로 대체
    기대: ResponseMismatchError 발생 (누락/과잉)
    """
    requested = [all_room_keys[0], all_room_keys[1], all_room_keys[2]]
    responded = [all_room_keys[0], all_room_keys[1], all_room_keys[3]]
    with pytest.raises(ResponseMismatchError) as excinfo:
        validate_response_rooms(requested, responded)
    assert "누락" in str(excinfo.value)
    assert "과잉" in str(excinfo.value)

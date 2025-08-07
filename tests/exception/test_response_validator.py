import pytest
from app.validate.response_validator import validate_response_rooms
from app.exception.common.response_exception import ResponseMismatchError
from app.models.dto import RoomKey
from pathlib import Path
import json

def load_roomkeys_from_json():
    """data/rooms.json 파일에서 RoomKey 리스트를 생성한다."""
    rooms_path = Path(__file__).parent.parent / "rooms.json"
    with open(rooms_path, encoding="utf-8") as f:
        rooms = json.load(f)
    return [RoomKey(**room) for room in rooms]

def test_validate_response_rooms_success():
    """
    요청: 실제 rooms.json에서 3개 방 선택
    응답: 같은 3개 방을 순서만 바꿔서 전달
    기대: 예외 발생하지 않음 (성공)
    """
    all_rooms = load_roomkeys_from_json()
    requested = [all_rooms[0], all_rooms[1], all_rooms[2]]
    responded = [all_rooms[2], all_rooms[0], all_rooms[1]]
    validate_response_rooms(requested, responded)

def test_validate_response_rooms_fail_count():
    """
    요청: 실제 rooms.json에서 3개 방 선택
    응답: 2개만 전달(1개 누락)
    기대: ResponseMismatchError 발생 (누락)
    """
    all_rooms = load_roomkeys_from_json()
    requested = [all_rooms[0], all_rooms[1], all_rooms[2]]
    responded = [all_rooms[0], all_rooms[1]]
    with pytest.raises(ResponseMismatchError) as excinfo:
        validate_response_rooms(requested, responded)
    assert "누락" in str(excinfo.value)

def test_validate_response_rooms_fail_id():
    """
    요청: 실제 rooms.json에서 3개 방 선택
    응답: 2개는 동일, 1개는 다른 방으로 대체
    기대: ResponseMismatchError 발생 (누락/과잉)
    """
    all_rooms = load_roomkeys_from_json()
    requested = [all_rooms[0], all_rooms[1], all_rooms[2]]
    responded = [all_rooms[0], all_rooms[1], all_rooms[3]]
    with pytest.raises(ResponseMismatchError) as excinfo:
        validate_response_rooms(requested, responded)
    assert "누락" in str(excinfo.value)
    assert "과잉" in str(excinfo.value)

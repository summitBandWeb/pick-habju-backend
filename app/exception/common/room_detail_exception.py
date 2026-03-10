from app.exception.base_exception import BaseCustomException

class RoomDetailFieldMissingError(BaseCustomException):
    """RoomDetail 필드 누락 시 발생하는 예외."""

    error_code = "Room-001"
    message = "RoomDetail 필드가 누락되었습니다."
    status_code = 400

class RoomDetailNotFoundError(BaseCustomException):
    """RoomDetail 조회 실패 시 발생하는 예외."""

    error_code = "Room-002"
    message = "RoomDetail이 존재하지 않습니다."
    status_code = 404

class RoomDetailListEmptyError(BaseCustomException):
    """rooms 목록이 비어 있을 때 발생하는 예외."""

    error_code = "Room-003"
    message = "rooms 목록이 비어 있습니다."
    status_code = 400

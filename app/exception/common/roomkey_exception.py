from app.exception.base_exception import BaseCustomException

class RoomKeyFieldMissingError(BaseCustomException):
    error_code = "Room-001"
    message = "RoomKey 필드가 누락되었습니다."
    status_code = 400

class RoomKeyNotFoundError(BaseCustomException):
    error_code = "Room-002"
    message = "RoomKey가 존재하지 않습니다."
    status_code = 404

class RoomKeyListEmptyError(BaseCustomException):
    error_code = "Room-003"
    message = "rooms 목록이 비어 있습니다."
    status_code = 400

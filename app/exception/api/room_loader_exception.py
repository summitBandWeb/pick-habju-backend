from app.exception.base_exception import BaseCustomException

class RoomLoaderFailedError(BaseCustomException):
    """룸 데이터 조회 실패"""
    error_code = "DATABASE-001"
    message = "룸 데이터 조회에 실패했습니다."
    status_code = 500
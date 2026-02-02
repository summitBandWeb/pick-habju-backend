from app.exception.base_exception import BaseCustomException

class InvalidDateFormatError(BaseCustomException):
    """날짜 형식이 잘못된 경우"""
    error_code = "Date-001"
    message = "날짜 형식이 잘못되었습니다."
    status_code = 422

class PastDateNotAllowedError(BaseCustomException):
    """과거 날짜는 허용되지 않을 때 발생"""
    error_code = "Date-002"
    message = "과거 날짜는 허용되지 않습니다."
    status_code = 400

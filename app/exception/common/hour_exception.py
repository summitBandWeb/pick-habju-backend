from app.exception.base_exception import BaseCustomException



class InvalidHourSlotError(BaseCustomException):
    """시간 형식이 잘못된 경우"""
    error_code = "Hour-001"
    message = "시간 형식이 잘못되었습니다."
    status_code = 422

class PastHourSlotNotAllowedError(BaseCustomException):
    """과거 시간은 허용되지 않을 때 발생"""
    error_code = "Hour-002"
    message = "과거 시간은 허용되지 않습니다."
    status_code = 400

class HourDiscontinuousError(BaseCustomException):
    """시간 입력이 연속적인 값이 아닐 경우"""
    error_code = "Hour-003"
    message = "연속적인 시간 값을 입력해야합니다."
    status_code = 422

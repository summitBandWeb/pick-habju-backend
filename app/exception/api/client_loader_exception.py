from app.exception.base_exception import BaseCustomException

class RequestFailedError(BaseCustomException):
    """외부 API 호출 실패(네트워크/상태코드/타임아웃 등)"""
    error_code = "API-001"
    message = "외부 API 호출에 실패했습니다."
    status_code = 503

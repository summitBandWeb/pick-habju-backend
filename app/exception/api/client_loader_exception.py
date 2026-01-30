from app.exception.base_exception import BaseCustomException, ErrorCode

class RequestFailedError(BaseCustomException):
    """외부 API 호출 실패(네트워크/상태코드/타임아웃 등)"""
    error_code = ErrorCode.API_REQUEST_FAILED
    message = "외부 API 호출에 실패했습니다."
    status_code = 503

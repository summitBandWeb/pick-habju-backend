from exception.base_exception import BaseCustomException

class RequestFailedError(BaseCustomException):
    """요청에 실패한 경우"""
    error_code = "Request-001"
    message = "요청에 실패"
    status_code = 502
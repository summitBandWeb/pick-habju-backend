class ErrorCode:
    """Error code constants."""

    GENERIC_UNKNOWN = "GENERIC-000"
    COMMON_INTERNAL_ERROR = "Common-001"
    API_REQUEST_FAILED = "API-001"


class BaseCustomException(Exception):
    error_code: str = ErrorCode.GENERIC_UNKNOWN
    message: str = "알 수 없는 오류가 발생했습니다."
    status_code: int = 400

    def __init__(self, message=None):
        if message:
            self.message = message
        super().__init__(self.message)

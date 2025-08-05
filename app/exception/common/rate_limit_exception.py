from app.exception.base_exception import BaseCustomException

class OverRateLimitError(BaseCustomException):
    error_code = "Rate-001"
    message = "일정 시간 내 너무 많은 요청이 발생했습니다."
    status_code = 429

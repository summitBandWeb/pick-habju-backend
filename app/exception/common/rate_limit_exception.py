from app.exception.base_exception import BaseCustomException

class RateLimitException(BaseCustomException):
    """요청 횟수(rate limit)가 초과되었을 때 발생."""
    error_code = "RateLimit-001"
    message = "요청 횟수가 초과되었습니다. 잠시 후 다시 시도해주세요."
    status_code = 429
